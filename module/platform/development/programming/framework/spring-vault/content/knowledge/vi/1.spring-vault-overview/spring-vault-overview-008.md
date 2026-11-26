# Trách nhiệm của thư viện so với trách nhiệm vận hành Vault

> **Chương:** Bản đồ Spring Vault  
> **Trọng tâm:** Spring Vault giúp ứng dụng Java **giao tiếp** với HashiCorp Vault. Việc Vault được triển khai an toàn, luôn sẵn sàng, có auth method, role, policy, secrets engine, audit và kế hoạch khôi phục thuộc trách nhiệm vận hành. Ứng dụng vẫn phải bảo vệ secret sau khi nhận, quản lý vòng đời các đối tượng đang sử dụng và xử lý lỗi đúng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân định trách nhiệm giữa **Spring Vault library**, **đội phát triển ứng dụng**, **đội vận hành Vault** và **đội an ninh/nền tảng**.
2. Giải thích vì sao `VaultTemplate` hoạt động tốt không có nghĩa Vault server đã được cấu hình an toàn hoặc có khả năng khôi phục khi sự cố.
3. Liệt kê những việc phải thực hiện ở Vault server: TLS, auth methods, roles, policies, secrets engines, audit, HA, seal/unseal, backup, DR và giám sát.
4. Mô tả hợp đồng tích hợp giữa hai bên gồm mount path, danh tính workload, policy, token TTL, secret lease, rotation, error handling và mức độ sẵn sàng.
5. Đọc ví dụ mã Java, policy HCL và luồng xác thực để xác định trách nhiệm khi KV v2 trả 403, token hết hạn hoặc Database credential bị thu hồi.
6. Thiết kế kế hoạch kiểm thử tích hợp và diễn tập sự cố theo đúng ranh giới trách nhiệm.

## 1. Tình huống mở đầu: thêm dependency rồi vẫn nhận 403

Một nhóm phát triển triển khai `orders-service` bằng Spring Boot. Nhóm thêm Spring Vault, inject `VaultOperations` và gọi KV v2:

~~~java
VaultResponse response = vault
    .opsForKeyValue("secret", KeyValueBackend.KV_2)
    .get("prod/orders/payment");
~~~

Ứng dụng biên dịch và kết nối HTTPS được đến Vault, nhưng Vault trả **403 permission denied**. Có người nói: “Spring Vault không hoạt động”. Thực tế, đường đi của yêu cầu có thể vẫn đúng:

- Java đã gọi đúng `VaultOperations` và HTTP client đã kết nối tới Vault.
- Vault đã nhận token hợp lệ của workload.
- Token lại **không có capability `read` trên `secret/data/prod/orders/payment`**.

Sửa phù hợp là đối chiếu **role → policy → API path** trong Vault với hợp đồng truy cập của workload. Không cần đổi sang root token, bỏ TLS hoặc sửa client để “bỏ qua” quyền. Nếu cấu hình mount/path Java sai, đội ứng dụng phải sửa code/cấu hình của mình; nếu policy chưa cấp đúng quyền được phê duyệt, đội quản trị Vault phải thay policy.

Tình huống này cho thấy **khả năng gọi API** và **quyền được Vault cho phép** là hai phần việc khác nhau.

## 2. Mô hình trách nhiệm tổng thể

~~~mermaid
flowchart LR
    subgraph APP["Ứng dụng Spring Boot (JVM)"]
        B["Business code<br/>Controller / Service"]
        C["Spring Vault client<br/>VaultOperations / VaultTemplate"]
        M["Authentication / SessionManager<br/>HTTP client + TLS"]
        B -->|"Gọi API Java"| C
        C --> M
    end

    W["Nền tảng workload<br/>ServiceAccount / IAM / AppRole bootstrap"] -->|"Bằng chứng danh tính"| M

    subgraph VAULT["Vault server / cluster"]
        A["Auth methods<br/>role, token, entity"]
        P["ACL policies<br/>path + capability"]
        E["Secrets engines<br/>KV / Database / Transit / PKI"]
        O["Hạ tầng vận hành<br/>HA, seal, storage, backup, audit"]
        A --> P
        P --> E
        O --> A
        O --> E
    end

    M <-->|"HTTPS /v1/..."| A
    M <-->|"HTTPS /v1/..."| P
    E -.->|"Nếu là Database engine"| D[("Cơ sở dữ liệu đích")]
    B -->|"Dùng credential đã cấp"| D
~~~

Các mũi tên quan trọng:

1. Từ `Controller/Service` đến `VaultOperations` là **lời gọi bên trong JVM**.
2. Từ Spring Vault client đến Vault là **HTTPS qua mạng**, chịu ảnh hưởng của DNS, TLS, latency và tình trạng cluster.
3. Việc cho phép request là **quyết định phía Vault server**, theo token và ACL policy trên path thực tế.
4. Khi một API key, DB password hoặc plaintext được trả về, nó nằm trong **bộ nhớ ứng dụng**. Vault không thể tự ngăn code Java ghi giá trị đó vào log hoặc response của REST API.
5. Các engine khác nhau có tác động khác nhau lên hệ thống đích: KV lưu secret, Database có thể phát hành tài khoản DB, Transit thực hiện thao tác mật mã, PKI phát hành chứng chỉ.

### Bốn chủ thể trong mô hình thực tế

| Chủ thể | Nhiệm vụ chính | Điều không nên giả định |
|---|---|---|
| **Thư viện Spring Vault** | Cung cấp API Java, chuyển request/response, cơ chế xác thực và quản lý phiên/lease theo cấu hình | Không tự tạo Vault cluster, bảo đảm HA hoặc quyết định role/policy |
| **Nhóm phát triển ứng dụng** | Chỉ định nhu cầu secret, gọi đúng API, bảo vệ dữ liệu đã đọc, xử lý timeout/rotation và cập nhật client đang dùng secret | Không thể coi đọc secret thành công là đã bảo mật toàn bộ nghiệp vụ |
| **Đội vận hành Vault / Platform / SRE** | Triển khai Vault, TLS, storage, HA, seal/unseal, backup/DR, auth/mount, audit, monitor, capacity | Không thể đảm bảo ứng dụng không log plaintext hoặc cập nhật đúng connection pool |
| **Đội an ninh/quản trị quyền** | Định nghĩa và phê duyệt quyền, identity trust, rotation, tiêu chuẩn audit và kiểm soát thay đổi | Policy chỉ giới hạn quyền API Vault; không thay phân quyền SQL hay authorization của Spring Security |

Một tổ chức nhỏ có thể để một nhóm đảm nhiệm nhiều vai trò. **Ranh giới trách nhiệm vẫn cần rõ**, ngay cả khi cùng một người vừa phát triển Java vừa vận hành Vault.

## 3. Ma trận trách nhiệm: ai phải tạo ra điều kiện để code chạy?

| Công việc | Bên chịu trách nhiệm chính | Spring Vault hỗ trợ đến đâu? | Bằng chứng cần kiểm tra |
|---|---|---|---|
| Chuẩn bị Vault server, storage và HA | Vault Ops / Platform | Chỉ kết nối đến endpoint | Endpoint ổn định, health và failover được thử |
| Khởi tạo cluster, seal/unseal hoặc auto-unseal | Vault Ops, Security | Không thực hiện thay quá trình vận hành | Quy trình khóa/mở khóa và recovery được kiểm thử |
| Cấu hình TLS/CA, DNS, network policy | Platform / Vault Ops | Java HTTP client sử dụng TLS/trust đã cấu hình | TLS handshake và hostname verification thành công |
| Bật auth method Kubernetes/AppRole/IAM | Vault Ops / Security | `ClientAuthentication` thực hiện login ở client | Workload đúng role đăng nhập được, role sai bị chặn |
| Viết policy, bind role và giới hạn TTL | Security / Vault Ops | Gửi token cùng yêu cầu đến path | Audit/policy test chứng minh capability đúng, không thừa |
| Bật KV v2/Database/Transit/PKI tại mount | Vault Ops | API phù hợp từng engine | Mount type/version và backend cấu hình đúng |
| Nạp secret tĩnh, thiết lập DB role/Transit key/PKI role | Chủ sở hữu secret + Vault Ops | Đọc/ghi/gọi API khi có quyền | Quy trình phát hành, kiểm soát thay đổi, xác minh downstream |
| Lập trình `VaultOperations`, exception handling, cache | App Dev | Cung cấp interface/implementation | Integration test đúng path, test lỗi timeout/403/404 |
| Quản lý Vault login token trong JVM | App Dev + library, với chính sách của Vault Ops | `SessionManager`/`ClientAuthentication` | Test expired/revoked/renewal theo loại token |
| Quản lý Database lease và thay pool | App Dev + Vault Ops/DBA | `SecretLeaseContainer` có thể hỗ trợ renew/rotate theo đăng ký | Test credential mới, connection pool rollover và revoke |
| Bật audit devices, bảo vệ sink và kiểm tra audit | Vault Ops / Security | Client có thể thêm correlation metadata phù hợp, không bật thay audit server | Audit pipeline hoạt động; log không lộ secret |
| Giám sát sức khỏe/backup/restore/DR | Vault Ops / SRE | Client báo lỗi, metrics ứng dụng | Alert, recovery drill và khả năng phục hồi |
| Bảo vệ secret trong heap, log, trace và REST response | App Dev | Không thể ngăn tùy ý code khác tiết lộ secret | Test không lộ token/password/plaintext |
| Kiểm soát quyền người dùng truy cập API nghiệp vụ | App Dev/Security, ví dụ Spring Security | Không xử lý authorization của caller REST | Web/method security và object ownership test |

**Bài học thực hành:** “Thêm Spring Vault” giải quyết phần **kết nối và sử dụng API từ Java**. Hạ tầng Vault và hợp đồng quyền phải sẵn sàng để request được thực thi hợp pháp và tin cậy.

## 4. Những phần thuộc vận hành HashiCorp Vault

### 4.1. Triển khai server, storage, HA và seal

Vault chạy thành một tiến trình/cụm độc lập, dùng storage backend và mô hình HA phù hợp. Với Vault tự quản lý, đội vận hành phải:

- Cấu hình node, listener, storage, địa chỉ API/cluster, khóa TLS, DNS/network và load balancer/service discovery nếu dùng.
- Khởi tạo Vault an toàn, quản lý unseal/recovery material theo quy trình phân quyền và lưu giữ; lựa chọn auto-unseal (nếu dùng) và bảo vệ quyền tới KMS/HSM tương ứng.
- Xử lý trạng thái **sealed**: khi Vault sealed, client không thể đơn giản thêm retry để lấy secret; cần khôi phục tình trạng server theo quy trình vận hành.
- Thiết kế topology HA, quorum, vùng lỗi và khả năng thay node; đánh giá hành vi failover đối với ứng dụng đang có request.
- Có chiến lược snapshot/backup, kiểm tra khôi phục và diễn tập DR; bản sao backup là tài sản nhạy cảm phải mã hóa, kiểm soát quyền và retention.

Spring Vault có thể kết nối thông qua địa chỉ Vault API được công bố; nó **không giữ unseal key, tự mở khóa cluster, quản lý quorum hoặc tạo bản sao backup**.

Với Vault được cung cấp dưới dạng dịch vụ quản lý, một phần hạ tầng (như vận hành node/storage/HA) có thể do nhà cung cấp đảm nhiệm theo hợp đồng. Khách hàng vẫn cần xác định ai quản lý **auth roles, policies, secrets engines, identity trust, audit, rotation, ứng dụng và bài kiểm thử DR**; không mặc nhiên cho rằng mọi trách nhiệm đều chuyển giao.

### 4.2. Auth method, workload identity và token policy

Khi ứng dụng chạy trên Kubernetes, có thể sử dụng ServiceAccount token để đăng nhập với **Kubernetes auth method** của Vault. Đội vận hành cần cấu hình endpoint auth, kết nối/trust với Kubernetes, role ràng buộc ServiceAccount và namespace cùng policies phù hợp; đội ứng dụng/nền tảng triển khai pod với danh tính đúng.

Ví dụ hợp đồng danh tính, không phải lệnh tự cấu hình server:

~~~yaml
workload: orders-service
namespace: prod
serviceAccount: orders-runtime
vaultAuthMount: auth/kubernetes
vaultAuthRole: orders-role
vaultPolicies:
  - orders-read-payment
vaultTokenTtl: defined-by-role-and-server-policy
~~~

Các tên chỉ là ví dụ kiến trúc. Việc Vault phát hành token còn phụ thuộc bằng chứng danh tính hợp lệ, ràng buộc auth role, cấu hình token và tình trạng server. Code Java **không nên có root token hoặc unseal key** để tự vượt qua quá trình xác thực.

Phân biệt:

- **Auth method:** xác minh workload và phát Vault token.
- **Token:** chứng từ dùng để gọi Vault API, có policy/TTL và điều kiện gia hạn/thu hồi.
- **Policy:** quy tắc Vault kiểm tra trên API path với capabilities như `read`, `create`, `update`, `list` và `delete`.
- **Spring `ClientAuthentication`:** cách Java cung cấp bằng chứng hoặc dùng token để tạo session; **không phải** policy engine.

### 4.3. Mount và cấu hình secrets engines

Chọn engine theo nghiệp vụ:

| Engine | Việc Vault Ops/Security phải cấu hình | Việc ứng dụng phải làm |
|---|---|---|
| **KV v2** | Enable mount/version, ACL data/metadata paths, retention/delete/destroy policy, quyền đọc/ghi | Dùng đúng mount + key logic, xử lý field/version thiếu, refresh khi key đổi |
| **Database** | Kết nối backend, database role/SQL grants, TTL/max TTL, khả năng revoke và secret backend credentials | Xin credential, theo dõi lease, cập nhật datasource/pool khi renew/reissue |
| **Transit** | Tạo key, loại key, quyền encrypt/decrypt/rewrap/rotate, bảo vệ key lifecycle | Gửi payload đúng format, giữ ciphertext, không log plaintext, xử lý key version |
| **PKI** | CA/issuer/roles, allowed names, TTL, chain, CRL/OCSP theo cấu hình và chính sách | Xin/ký certificate, giữ private key an toàn, nạp lại TLS context trước hạn |
| **Auth/token** | Auth mounts, roles, policies, TTL/max TTL/renewability, identity mappings | Login bằng workload, dùng session hợp lệ, xử lý expire/revoke |

Một mount chẳng hạn `secret/` **không mặc nhiên tồn tại** trên mọi Vault server; tên mount và loại engine do quản trị viên cấu hình. Khi đổi mount, cả client path và policy path cần được đối chiếu, không chỉ đổi một đoạn chuỗi trong Java.

### 4.4. Audit, giám sát và quản trị thay đổi

Vault cung cấp audit devices và các nguồn quan sát ở phía server. Đội vận hành phải bật, bảo vệ và giám sát audit sinks, bảo đảm hệ thống ghi nhận yêu cầu có cơ chế hạn chế lộ dữ liệu nhạy cảm theo chính sách. Hệ thống cần phân biệt **log truy cập API**, **sức khỏe cluster**, **lỗi auth/policy**, **latency/throughput** và **tuổi thọ token/lease**.

Mọi thay đổi auth role, policy, mount, Transit key, PKI issuer hoặc Database role nên được review, quản lý phiên bản và thử nghiệm. Có thể sử dụng hạ tầng dưới dạng mã (IaC) và quy trình triển khai của tổ chức; Spring Vault không thay thế quy trình kiểm soát thay đổi hạ tầng.

## 5. Thư viện Spring Vault thực sự làm gì?

Spring Vault là client library trong ứng dụng Java. Các abstraction chính:

| API hoặc thành phần | Vai trò tại client | Điều kiện phải có ở phía Vault |
|---|---|---|
| `VaultOperations` | Interface đọc/ghi/xóa/gọi operations | Token có quyền với path |
| `VaultTemplate` | Implementation đồng bộ thực hiện request, mapping response và phối hợp session/transport | Vault API có thể kết nối và secrets engine đúng |
| `VaultEndpoint` | Xác định URL host/port/scheme của server | DNS, listener và TLS phù hợp |
| `ClientAuthentication` | Chiến lược lấy login token hoặc dùng token đã có | Auth method, trust/role và credential bootstrap hợp lệ |
| `SessionManager` | Cung cấp token cho các Vault requests | TTL, renewability và điều kiện theo policy |
| `LifecycleAwareSessionManager` | Hỗ trợ vòng đời/renew token đăng nhập đủ điều kiện | Server cho phép renew; token không bị revoke |
| `VaultKeyValueOperations` | API KV v1/v2 ở mức mount + key logic | Mount KV đúng version; `read`/`write` theo path |
| `SecretLeaseContainer` | Theo dõi và quản lý lease cho paths/secret đã đăng ký | Engine phát lease/renew/revoke theo cấu hình |
| `VaultPropertySource` | Đưa dữ liệu Vault vào `Environment` của Spring | Secret/config context có quyền đọc |

Spring Cloud Vault có thể dùng cơ chế client này để nạp config từ Vault qua Config Data, chẳng hạn `spring.config.import: vault://`. Điều đó cũng **không** khiến Spring sở hữu Vault server hoặc tự đảm nhiệm backup, audit hay policy.

### 5.1. Một ví dụ Java chỉ làm đúng trách nhiệm client

Giả sử Vault Ops đã bật KV v2 tại mount `secret`, key logic `prod/orders/payment` và cấp policy đọc cho `orders-service`. Đội ứng dụng chỉ cần inject client đã cấu hình và dùng đúng key:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class PaymentSecretGateway {

    private final VaultKeyValueOperations kv;

    public PaymentSecretGateway(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
            "secret", KeyValueBackend.KV_2);
    }

    public String getPaymentApiKey() {
        VaultResponse result = kv.get("prod/orders/payment");
        if (result == null) {
            throw new IllegalStateException(
                "Required payment secret was not found");
        }
        Object value = result.getRequiredData().get("api-key");
        if (!(value instanceof String key) || key.isBlank()) {
            throw new IllegalStateException(
                "Required payment secret field is missing");
        }
        return key;
    }
}
~~~

Mã trên minh họa code dùng `VaultOperations`; nó **giả định bean đã có** với endpoint, TLS và workload authentication đúng. Mã không tự cấu hình Vault auth method, không tạo `secret/` và không đặt chính sách truy cập.

### 5.2. Phần còn thiếu ở server: policy HCL

Vault operator/security có thể cấp policy tối thiểu:

~~~hcl
# KV v2 mount secret/, key logic prod/orders/payment.
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

So sánh ba đường dẫn:

~~~text
Spring KV API:   get("prod/orders/payment")
Vault HTTP API:  GET /v1/secret/data/prod/orders/payment
Vault policy:    secret/data/prod/orders/payment
~~~

Đoạn `data/` thuộc KV v2 API; `/v1/` là prefix HTTP **không được đưa vào Vault policy**. Thư viện có thể giúp Java không cần tự ghép HTTP path ở API KV cấp cao, nhưng policy vẫn được kiểm tra phía server.

Nếu ứng dụng cần `list` KV v2, quyền thường phải nằm trên `secret/metadata/...`, không tự xuất hiện từ quyền `read`. Một số cơ chế auto-detection backend cũng có thể truy cập endpoint nội bộ như `sys/internal/ui/mounts/...`; cần kiểm tra behavior theo phiên bản thật trước khi mở quyền bổ sung.

### 5.3. Spring Vault không tự quản lý vòng đời mọi đối tượng của ứng dụng

`VaultTemplate` lấy được một database password không có nghĩa nó đã **thay password trong HikariCP**, đóng connection cũ hoặc chuyển giao transaction. Tương tự, `SecretLeaseContainer` có thể tạo sự kiện khi credential/lease thay đổi, nhưng ứng dụng phải **đăng ký đúng paths** và tích hợp sự kiện vào nơi tiêu thụ secret.

Một giá trị được Spring Cloud Vault nạp vào `Environment` cũng không làm mọi bean giữ giá trị cũ tự động cập nhật. Trong hầu hết hệ thống, ứng dụng phải thiết kế rõ thời điểm refresh/rebuild và cách xử lý downtime.

## 6. Hợp đồng tích hợp giữa App Dev và Vault Ops

Trước khi viết service, hai nhóm nên xác định một **integration contract**. Mục tiêu là mọi team nhìn cùng một định nghĩa, test được và biết nơi báo lỗi.

| Thuộc tính | Ví dụ cho `orders-service` | Ai quyết định/xác minh? |
|---|---|---|
| Vault endpoint | `https://vault.internal.example:8200` | Vault Ops công bố; App Dev kiểm tra TLS/kết nối |
| Auth method/mount | Kubernetes tại `auth/kubernetes` | Platform/Security cấu hình; App Dev dùng đúng |
| Workload identity | ServiceAccount `orders-runtime`, namespace `prod` | Platform cấp; Security ràng buộc role |
| Vault auth role | `orders-role` | Vault Ops/Security |
| Login token TTL | Theo role/policy được phê duyệt | Vault Ops; App Dev kiểm thử expired/renew |
| KV engine | KV v2, mount `secret` | Vault Ops tạo; App Dev dùng `KV_2` |
| KV key logic | `prod/orders/payment` | Chủ sở hữu secret và App Dev thống nhất |
| Vault ACL path | `secret/data/prod/orders/payment` | Security cấp `read` |
| Dữ liệu trả về | Field `api-key`, không chứa các field không cần thiết | Chủ sở hữu secret quy định schema |
| Rotation | Đối tác phát hành key mới; ứng dụng refresh theo kế hoạch | Chủ sở hữu secret và App Dev phối hợp |
| Timeout/retry | Giới hạn theo SLO, đặc tính endpoint | App Dev + SRE |
| Quan sát/audit | Các lỗi theo loại, không log secret | App Dev phát metrics; Vault Ops quản lý audit |
| Diễn tập khôi phục | Khi Vault unavailable/sealed/token revoke | SRE/Vault Ops phối hợp App Dev |

Hợp đồng này cần sống trong hệ thống tài liệu và quy trình thay đổi của tổ chức. Khi đổi tên mount, role, KV version hoặc auth method, cập nhật **cả cấu hình client, policy, integration test và kế hoạch deploy**.

### 6.1. Luồng triển khai phối hợp

~~~mermaid
sequenceDiagram
    autonumber
    participant SEC as Security / Owner
    participant OPS as Vault Ops
    participant APP as App Dev
    participant CI as Pipeline / Test Vault

    APP->>SEC: Đề xuất workload + dữ liệu cần đọc + thao tác
    SEC-->>OPS: Phê duyệt role/policy tối thiểu
    OPS->>OPS: Chuẩn bị auth, mount, policy, secret/engine
    OPS-->>APP: Contract: endpoint, mount, path, TTL, role
    APP->>CI: Build app với Vault client config
    CI->>OPS: Test login/path/policy trên môi trường test
    OPS-->>CI: Allow/deny và audit theo cấu hình
    CI-->>APP: Kết quả integration/negative tests
    APP->>OPS: Thống nhất giám sát và runbook trước rollout
~~~

Một quy trình hiệu quả phải có **negative test**: service đọc được chính secret của nó nhưng **không đọc được** secret của service khác. Login thành công đơn lẻ chưa đủ chứng minh least privilege.

## 7. Vòng đời token và lease: trách nhiệm ở hai đầu

### 7.1. Vault login token

Đội Vault Ops quyết định auth method, điều kiện trust, TTL/max TTL, khả năng renew và policy của token. `ClientAuthentication` cung cấp cơ chế đăng nhập cho Java; `SessionManager` làm việc với token đã nhận. `LifecycleAwareSessionManager` có thể hỗ trợ gia hạn token hợp lệ; tuy nhiên không phải loại token nào cũng renewable hoặc có thể renew vô hạn.

**Hết hạn Vault token** nghĩa là client có thể không gọi được Vault tiếp cho tới khi renew hoặc login lại hợp lệ. Token bị revoke có thể tác động tới các lease liên quan; ứng dụng cần kiểm tra điều đó theo engine/trường hợp cụ thể.

### 7.2. Database dynamic credential và lease

Đội vận hành cấu hình Database engine connection, role phát account, các quyền SQL, default/max TTL và hành vi revoke. Khi app đọc:

~~~text
GET /v1/database/creds/orders-reader
~~~

Vault có thể trả username/password động, `lease_id`, `lease_duration` và `renewable`. Lease này có vòng đời riêng với Vault login token.

~~~mermaid
flowchart TB
    ISSUE["Vault Database engine<br/>issue credential A + lease"] --> POOLA["Spring datasource/pool A"]
    POOLA --> TX["Transaction đang chạy"]
    EXP{"A gần hết lease?"} -->|"Renew được"| RENEW["Renew có giới hạn<br/>theo policy"]
    EXP -->|"Không renew"| NEW["Issue credential B"]
    RENEW --> POOLA
    NEW --> POOLB["Ứng dụng tạo pool B<br/>dành cho kết nối mới"]
    POOLB --> CUT["Drain pool A / chuyển traffic"]
    TX --> CUT
    CUT --> REVOKE["Revoke/expire A<br/>theo chiến lược"]
~~~

Hành vi thực tế của connection đang mở khi credential bị revoke phụ thuộc database, driver, pool và backend; không suy diễn mọi socket đang có lập tức đóng. Spring Vault hỗ trợ theo dõi lease ở mức client, **nhưng không thể thay thế thiết kế của datasource**.

### 7.3. KV rotation, Transit key và PKI certificate

| Loại thay đổi | Vault Ops / chủ sở hữu secret | App Dev |
|---|---|---|
| **API key KV v2** | Cấp/nhập version mới, phối hợp thu hồi tại đối tác, retention các version cũ | Invalidate cache/reload client, kiểm tra lỗi 401 từ nhà cung cấp |
| **Transit key rotation** | Kiểm soát key versions, quyền encrypt/decrypt/rewrap và giới hạn decrypt versions | Lưu ciphertext, rewrap hoặc mã hóa lại dữ liệu cũ khi cần, không log plaintext |
| **PKI certificate** | CA/role/TTL/chain/revocation và cấp phát hợp lệ | Bảo vệ private key, cấp lại, thay keystore/TLS context và kết nối đang dùng |
| **Database dynamic creds** | Lease/TTL/revoke, SQL grants/backend account management | Xin credential mới, cập nhật connection pool, xử lý sự cố khi đổi |

**KV version khác lease TTL, lease TTL khác Vault token TTL.** Transit ciphertext không mang lease DB; certificate có hạn hiệu lực X.509 và chu trình thay TLS context riêng. Một quy trình rotation chung áp máy móc cho mọi engine sẽ gây lỗi.

## 8. Xử lý sự cố: xác định đúng đội và hành động

### Bảng chẩn đoán nhanh

| Triệu chứng quan sát | Kiểm tra đầu tiên | Trách nhiệm chính | Không nên làm |
|---|---|---|---|
| Ứng dụng không có bean `VaultOperations` | Dependency, config, bean wiring, profile | App Dev | Thay role Vault khi ứng dụng chưa gọi API |
| DNS/connect timeout tới Vault | Endpoint, DNS, network policy, route | Platform/SRE cùng App Dev | Hard-code secret để bỏ qua lỗi mà không có phương án an toàn |
| TLS handshake fail | CA trust, hostname, certificate, clock | Platform/Vault Ops + App Dev | Tắt TLS verification |
| Auth login bị từ chối | Workload identity, auth role, audience/trust, token source | Security/Vault Ops/Platform | Chuyển sang root token |
| Vault trả 403 tại KV read | Token/policy trên API path, KV v1/v2, role | Security/Vault Ops, App Dev xác nhận path | Cấp `path "*"` hoặc retry mãi với token cũ |
| Vault trả 404 hoặc field trống | Key/mount/version, schema response, dữ liệu bị xóa | Secret Owner + App Dev + Vault Ops | Coi 404 như 403, hoặc lấy giá trị mặc định không an toàn |
| Vault ở trạng thái sealed | Health/seal state, quá trình unseal/auto-unseal | Vault Ops/SRE | Mong `VaultTemplate` mở seal |
| Vault 5xx/429 hoặc quá tải | Cluster/engine health, rate limits, latency | Vault Ops/SRE; App Dev giảm tải | Retry vô hạn hoặc retry thao tác cấp phát không idempotent |
| Login token expired/revoked | TTL, renewability, auth strategy, session | App Dev + Vault Ops | Giả định token không bao giờ hết hạn |
| Database credential không còn hợp lệ | Lease/revoke/role và connection pool | App Dev + Vault Ops/DBA | Chỉ gia hạn Vault token rồi bỏ qua DB lease |
| Transit encrypt lỗi | Key/role/policy, payload encoding, crypto engine | App Dev + Vault Ops | Lưu plaintext khi Vault unavailable |
| PKI cert hết hạn | PKI TTL/role/issuer và cơ chế reload TLS | Vault Ops + App Dev | Chỉ cấp cert mới mà không nạp vào process |
| Audit không có sự kiện | Audit device/sink/permissions và đường đi request | Vault Ops/Security | Tin rằng log client thay thế được audit server |

Không nên gộp mọi lỗi vào một exception “không có secret”. Ví dụ:

- **403:** Vault đã từ chối quyền; cần kiểm tra policy/role/path, retry cùng quyền thường không đổi kết quả.
- **404:** mount, key, version hoặc resource không có; cần kiểm tra dữ liệu và phiên bản backend.
- **TLS/network:** client không hoàn tất yêu cầu an toàn; sửa hạ tầng hoặc cấu hình tin cậy.
- **5xx/429/timeout:** có thể tạm thời; chọn retry hữu hạn, backoff + jitter và xem xét tính idempotent của endpoint.

Với dữ liệu bắt buộc để xác thực hoặc mã hóa, khi Vault không sẵn sàng hoặc policy từ chối, ứng dụng nên **fail closed** theo nghiệp vụ. Điều đó có nghĩa từ chối thao tác phụ thuộc secret thay vì tự bỏ qua xác thực/mã hóa hoặc sử dụng credential mặc định.

### 8.1. Một runbook ngắn cho lỗi 403 KV v2

1. **App Dev:** xác nhận operation dùng `opsForKeyValue("secret", KV_2).get("prod/orders/payment")` và endpoint đúng. Không log giá trị token.
2. **Vault Ops/Security:** xác định danh tính và policies của token từ dữ liệu kiểm toán/kiểm tra an toàn; đối chiếu `read` trên `secret/data/prod/orders/payment`.
3. **Security:** nếu quyền đó đã được phê duyệt nhưng thiếu, sửa policy/role qua change process; nếu quyền chưa được phép, yêu cầu ứng dụng đổi thiết kế.
4. **App Dev + CI:** chạy lại test đọc đúng path và negative test không đọc được secret ngoài scope.
5. **SRE:** theo dõi 403/error rate và xác nhận không còn lặp lại ở môi trường triển khai.

Không ghi nguyên token, secret hoặc response plaintext vào ticket/runbook. Thông tin chẩn đoán nên gồm service, environment, operation, status và path ở mức phù hợp chính sách tổ chức.

## 9. Sẵn sàng cao, khôi phục và hành vi ứng dụng khi Vault gián đoạn

Vault là một phụ thuộc hạ tầng trọng yếu. **HA server** và **chịu lỗi ở client** bổ sung nhau nhưng không thay thế nhau.

### Phía Vault Ops cần

- Theo dõi trạng thái cluster, quorum/storage, leader/standby hoặc mô hình active nodes theo khả năng edition/triển khai.
- Bảo vệ TLS, network access và những dependencies như KMS/auto-unseal.
- Có backup/snapshot và quy trình khôi phục đã **thử trên môi trường cô lập**, với mục tiêu RPO/RTO rõ ràng.
- Diễn tập failover, khôi phục khi sealed, lỗi storage, mất một vùng hạ tầng và sai cấu hình policy/engine.
- Bảo đảm audit sinks có sẵn và không tạo điểm đơn lỗi ngoài thiết kế.

### Phía ứng dụng cần

- Thiết lập connect/read timeouts, giới hạn retry phù hợp, tránh thác request dồn vào Vault khi Vault lỗi.
- Giới hạn số lần lấy secret theo request; đánh giá cache cho KV tĩnh, nhưng tránh cache vĩnh viễn một credential có khả năng bị thu hồi.
- Xác định startup behavior khi cấu hình bắt buộc không thể đọc: fail có kiểm soát hoặc degraded mode **chỉ khi nghiệp vụ cho phép**.
- Với Transit hoặc PKI đang cần hoạt động runtime, xử lý lỗi rõ ràng vì không thể tùy ý tự thực hiện crypto bằng key không được cấp.
- Thiết kế refresh/rotation và nạp lại client/datasource/TLS context; không dựa vào restart ngẫu nhiên để sửa hết hạn credential.

Một cache KV tĩnh không thể thay chức năng của Database lease; một ciphertext đã nhận trước đó không cho phép tiếp tục gọi Transit decrypt khi Vault vắng mặt. Cần phân biệt **dữ liệu đang có** và **quyền/tác vụ phải yêu cầu lại từ Vault**.

## 10. Giám sát và kiểm toán: hai phía nhìn cùng sự cố

### 10.1. Chỉ số phía ứng dụng

Theo dõi số request đến Vault theo nhóm operation, latency, tỷ lệ timeout, 403/404/5xx, tần suất login/renew, thời gian gần hết hạn credential/certificate, số lần refresh cache và tỷ lệ lỗi nghiệp vụ downstream. Metric labels nên là thông tin đã đánh giá an toàn như service, loại thao tác, environment và status code.

Không đưa API key, Vault token, private key, Transit plaintext, database password hay nội dung response vào **logs, traces hoặc metrics labels**. Bảo vệ `/actuator/env`, `/actuator/configprops`, heap dump và các công cụ debug có thể truy cập dữ liệu nhạy cảm.

### 10.2. Chỉ số và audit phía Vault

Đội vận hành theo dõi sức khỏe node, storage, seal state, auth failures, policy denials, audit delivery, TTL/lease hoạt động, latency engine và resource utilization. Vault audit giúp truy vết request/response theo cấu hình audit device và khả năng bảo vệ dữ liệu; **không thay thế** việc kiểm tra các secret đã bị ứng dụng in ra log.

### 10.3. Phối hợp phân tích nguyên nhân gốc

Một yêu cầu thất bại có thể trải qua bốn tầng:

~~~text
REST user request
  -> Spring Security / business authorization
  -> Spring Vault client: auth, session, TLS, timeout
  -> Vault server: auth method, token, policy, secrets engine
  -> Hệ thống đích: PostgreSQL / payment / TLS peer
~~~

Lỗi 403 do Vault khác lỗi 403 do Spring Security ở REST API. Credential DB do Vault cấp thành công vẫn có thể bị DB từ chối vì SQL grants hoặc lease đã hết. Tổ chức phải gắn **owner xử lý sự cố cho từng tầng** và định nghĩa correlation ID/metrics an toàn để ghép các sự kiện mà không lộ secret.

## 11. Kiểm thử tích hợp: chứng minh cả hợp đồng, không chỉ code gọi hàm

Unit test mock `VaultOperations` chỉ chứng minh code đọc đúng field và xử lý response giả. Để xác nhận tích hợp thật, cần Vault server **cô lập dành cho test** với auth, policy và mount được dựng tương đương môi trường mục tiêu; khi thử Database secrets engine, cần database test phù hợp.

| Bài kiểm thử | App Dev kiểm tra | Vault Ops/Security cung cấp/xác minh |
|---|---|---|
| **Kết nối TLS** | Client trust CA, hostname verification, timeout | Listener/certificate và chính sách mạng |
| **Auth workload** | Login bằng identity đúng; xử lý 401/403 của auth | Auth mount/role gắn đúng namespace/service account |
| **KV v2 read** | `VaultOperations` dùng đúng key logic và phân tích response | Mount version, `read` trên `secret/data/...` |
| **Negative policy** | App không nhận secret ngoài scope | Role/policy deny ngoài path phê duyệt |
| **Token revoke/expire** | Session reconnect/renew hoặc fail theo thiết kế | Token TTL/renewability và thử revoke |
| **DB dynamic creds** | Xin credential mới, thay pool, xử lý lease hết hạn | Database engine role, TTL/revoke thực tế |
| **Transit encrypt** | Base64 payload, ciphertext, không fallback plaintext | Key/role, quyền encrypt nhưng không decrypt nếu không cần |
| **PKI issuance/rotation** | Nhận certificate, reload TLS context, kết nối mới thành công | PKI CA/role, TTL và revocation |
| **Vault failover/unavailable** | Timeout/retry hữu hạn và degraded/fail closed | HA/failover, seal/health, backup recovery |
| **Audit và dữ liệu nhạy cảm** | Log/trace/metrics không chứa secret | Audit pipeline nhận được sự kiện cần thiết |

Test nên có dữ liệu giả và không dùng token/credential sản xuất. Các bài diễn tập failover, sealed state và DR cần thực hiện trên môi trường/hạ tầng được cho phép và lên kế hoạch riêng; không chủ động tác động một Vault production chỉ để kiểm tra ứng dụng.

### Ví dụ yêu cầu chấp nhận đối với release

~~~text
GIVEN:
  orders-service xác thực bằng ServiceAccount orders-runtime
  Vault KV v2 tại secret/
  Key prod/orders/payment có field api-key giả
  Policy chỉ cho read key đó

WHEN:
  ứng dụng gọi PaymentSecretGateway.getPaymentApiKey()

THEN:
  nhận được field api-key với giá trị test
  không có secret trong log/REST response
  truy cập secret của service khác bị Vault từ chối
  token hết hạn và Vault timeout được xử lý đúng chính sách
~~~

Kịch bản này đòi hỏi **hai phía cùng hoạt động**. Không thể chứng minh policy deny chỉ bằng mock Java, cũng không thể chứng minh bảo vệ bộ nhớ/log chỉ bằng server audit.

## 12. Bài tập phân định trách nhiệm

### Tình huống A — Service kết nối được nhưng không đọc được secret

Vault trả 403 dù token còn hiệu lực. Hãy xác minh mount KV v2, key logic, policy `secret/data/...` và role được gắn vào workload. **Vault Ops/Security** chịu trách nhiệm cấp đúng quyền đã duyệt; **App Dev** chịu trách nhiệm gửi đúng path và xử lý lỗi không tiết lộ secret.

### Tình huống B — Vault server sealed sau một sự cố hạ tầng

Nhiều service cùng không thể đọc secret. Mã `VaultTemplate` và policy không thay đổi. **Vault Ops/SRE** xác minh cluster, KMS/auto-unseal và quy trình unseal/recovery. **App Dev** đảm bảo startup/runtime timeout, retry có giới hạn và trạng thái degraded/fail-closed phù hợp.

### Tình huống C — DB credentials vừa được rotate nhưng ứng dụng vẫn dùng account cũ

Vault đã cấp credential mới theo role nhưng connection pool giữ username/password cũ. **App Dev** phải tái tạo/cập nhật datasource và quản lý kết nối; **Vault Ops/DBA** kiểm tra lease/revoke và quyền SQL. Không thể quy lỗi chỉ cho `SecretLeaseContainer`.

### Tình huống D — Không thể giải mã dữ liệu sau khi Transit key thay phiên bản

Kiểm tra Transit key version, quyền decrypt/rewrap, chính sách min decryption version và quy trình rewrap dữ liệu cũ. **Vault Ops/Security** quyết định key policy và giới hạn phiên bản; **App Dev** quản lý ciphertext, migration và xử lý lỗi. Không tự lưu plaintext vì thao tác decrypt bị từ chối.

### Tình huống E — Audit phía Vault đầy đủ nhưng secret vẫn bị lộ

Service trả nguyên API key trong JSON response của REST endpoint. Vault đã kiểm tra token/policy đúng; **App Dev/Security** phải sửa authorization và luồng trả dữ liệu. Audit Vault không thể ngăn service đã được phép đọc secret tự tiết lộ dữ liệu cho người khác.

### Câu hỏi tự kiểm tra

1. Spring Vault có thể thay Vault Ops bật auth method và tạo HA cluster không? Vì sao?
2. `VaultTemplate` làm gì, còn Vault server quyết định điều gì khi request trả 403?
3. Trong KV v2, `get("prod/orders/payment")` tương ứng policy path nào nếu mount là `secret/`?
4. Vì sao `LifecycleAwareSessionManager` và `SecretLeaseContainer` không thay thế kế hoạch làm mới datasource?
5. Khi cluster sealed, ai cần thực hiện thao tác khôi phục và ứng dụng nên phản ứng thế nào?
6. Đội nào chịu trách nhiệm với việc một API key đã đọc bị in vào log? Vault audit có ngăn được không?
7. Vì sao diễn tập HA/DR và kiểm thử negative policy phải được thực hiện ngoài unit test mock Java?
8. Với Transit và PKI, điều gì thuộc Vault key/certificate policy và điều gì thuộc mã ứng dụng sử dụng kết quả?

## 13. Tổng kết

Spring Vault là **thư viện client** trong JVM: nó giúp ứng dụng Java dùng `VaultTemplate`/`VaultOperations`, xác thực theo workload và trao đổi với Vault qua HTTP/TLS. HashiCorp Vault server là **hệ thống thực thi quyền và quản lý bí mật**: server cần auth methods, roles, policies, mounts, storage, HA, seal management, audit, backup và vận hành an toàn.

Điểm giao nhau là **hợp đồng tích hợp** gồm identity, auth role, token TTL, mount/path, capability, response schema, lease/rotation và hành vi khi lỗi. Đội vận hành tạo các điều kiện tin cậy; Spring Vault thực hiện lời gọi; đội ứng dụng chịu trách nhiệm bảo vệ dữ liệu và vận hành đúng các client, pool và TLS context sau khi nhận secret. Chỉ khi ba phần này phối hợp, việc đưa secret ra khỏi mã nguồn mới thực sự cải thiện kiểm soát truy cập và vòng đời.

## Tài liệu tham khảo chính thức

- [Spring Vault — Reference Documentation](https://docs.spring.io/spring-vault/reference/)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Authentication Methods](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — Secret Lease Container](https://docs.spring.io/spring-vault/reference/vault/secret-lease-container.html)
- [HashiCorp Vault — How Vault Works](https://developer.hashicorp.com/vault/docs/about-vault/how-vault-works)
- [HashiCorp Vault — Authentication Methods](https://developer.hashicorp.com/vault/docs/auth)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — High Availability](https://developer.hashicorp.com/vault/docs/concepts/ha)
- [HashiCorp Vault — Seal and Unseal](https://developer.hashicorp.com/vault/docs/concepts/seal)
- [HashiCorp Vault — Audit Devices](https://developer.hashicorp.com/vault/docs/audit)
- [HashiCorp Vault — Integrated Storage](https://developer.hashicorp.com/vault/docs/configuration/storage/raft)
- [HashiCorp Vault — KV v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2)
- [HashiCorp Vault — Database Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/databases)
- [HashiCorp Vault — Transit Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
- [HashiCorp Vault — PKI Secrets Engine](https://developer.hashicorp.com/vault/docs/secrets/pki)

> **Lưu ý khi triển khai:** Chính xác những vai trò nào do đội nội bộ hay nhà cung cấp quản lý phụ thuộc hình thức Vault self-managed/managed, phiên bản và hợp đồng dịch vụ. Các tên role, mount, path và địa chỉ ở bài chỉ là dữ liệu giả để học. Phải đối chiếu tài liệu phiên bản thực tế và kiểm thử trên môi trường riêng trước khi áp dụng cho production.
