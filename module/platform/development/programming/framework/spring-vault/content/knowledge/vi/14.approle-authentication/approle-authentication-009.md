# Cấp SecretId mới khi triển khai lại ứng dụng

## 1. Mục tiêu và bài toán triển khai thực tế

Trong chương **Xác thực AppRole** của **SPRING_VAULT**, một ứng dụng Java có thể sử dụng `AppRoleAuthentication` để đăng nhập HashiCorp Vault bằng **RoleID + SecretID**. Tuy nhiên, một SecretID được cấp cho lần khởi chạy trước **không đương nhiên dùng lại được** ở lần triển khai tiếp theo: nó có thể hết thời hạn, hết số lượt đăng nhập, bị thu hồi hoặc đã được chuyển giao dưới dạng response wrapping token dùng một lần.

Bài học này trả lời câu hỏi chính: **làm thế nào cấp SecretID mới cho từng lần deploy/redeploy, rolling update hoặc autoscaling mà không hard-code credential, không tái sử dụng token đã tiêu thụ và không làm gián đoạn service?**

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa **phiên bản ứng dụng**, **instance**, **AppRole**, **SecretID** và **client token**.
- Thiết kế một quy trình deploy trong đó provisioner phát **SecretID mới cho instance mới**, giữ RoleID ổn định khi phù hợp và phân phối credential bằng kênh tin cậy.
- Sử dụng `vault write -wrap-ttl=... -f auth/approle/role/<role>/secret-id` để chuyển một **wrapping token ngắn hạn**, rồi cấu hình `SecretId.wrapped(...)` trong Spring Vault.
- Lựa chọn giữa `SecretId.provided(...)`, `SecretId.pull(...)` và `SecretId.wrapped(...)` theo vòng đời thực tế.
- Xử lý rolling deployment, blue-green, rollback, retry pipeline, autoscaling, credential hết hạn và tình huống unwrap bị gián đoạn.
- Hiểu cách SecretID TTL/số lượt, Vault client token, `SessionManager` và policy KV v2 tương tác.
- Xây checklist vận hành và test tích hợp chứng minh ứng dụng mới lấy được token hợp lệ, còn request ngoài quyền bị từ chối.

Ví dụ sử dụng **Spring Vault Core 4.1.x**, Java 17+, HashiCorp Vault AppRole và KV v2. Các lệnh HTTP local chỉ dành cho **lab/test**; production phải dùng HTTPS/TLS được xác minh. Không đưa credential thực vào source code, Docker image, CI output, ticket hoặc tài liệu.

## 2. Vì sao redeploy cần xem xét SecretID mới?

Giả sử `report-worker` có:

- RoleID `R` được Vault tạo và gắn với AppRole `report-worker`.
- SecretID `S1` đã cấp cho instance phiên bản `v1`.
- Vault client token `T1` nhận sau khi `v1` đăng nhập thành công.
- Pipeline chuẩn bị chạy phiên bản `v2` trên một instance mới.

Nếu `S1` có `secret_id_num_uses=1` thì chỉ lần đăng nhập đầu tiên bằng `S1` dùng được. Nếu `S1` có TTL 10 phút, một instance khởi động lại sau 10 phút cũng không thể dùng credential đó để login mới. Nếu `S1` được chuyển dưới dạng **wrapping token `W1`** thì `W1` đã hết giá trị ngay khi instance `v1` unwrap một lần.

Để instance `v2` đăng nhập, provisioner phát **`S2` và, nếu dùng wrapping, `W2`**. RoleID có thể giữ nguyên nếu role không thay đổi. Đổi image từ `v1` sang `v2` **không** làm Vault tự tạo SecretID mới.

### 2.1. Phân biệt những thứ nào được tái sử dụng

| Thành phần | Có thể giữ qua redeploy? | Điều kiện |
| --- | --- | --- |
| **Tên AppRole** (`report-worker`) | Có | Quyền và cấu hình role còn phù hợp |
| **RoleID** | Thường có | RoleID chưa bị thay/thu hồi và vẫn được cấp qua kênh an toàn |
| **SecretID** | Không nên mặc định | Chỉ tái sử dụng nếu TTL/lượt/ràng buộc còn cho phép; ưu tiên cấp riêng theo instance |
| **Wrapping token** | **Không**, khi đã unwrap | Token dùng một lần; mỗi deploy/instance cần token mới |
| **Vault client token** | Không nên sao chép giữa instance | Token gắn policy, TTL, bối cảnh phiên và cách quản lý riêng |
| **Docker image/JAR** | Có thể tái sử dụng | Credential phải được inject **khi chạy**, không nhúng vào artifact |

**Nguyên tắc:** triển khai lại cùng một image vẫn là **một phiên bootstrap mới**, nên cấp credential theo **instance/run mới**, không theo mã phiên bản image. Rollback image không đồng nghĩa rollback SecretID.

### 2.2. Bốn vòng đời độc lập

~~~mermaid
flowchart LR
    A["Deploy instance v2"] --> B["Provisioner phát SecretID S2"]
    B --> C["Vault response-wrap thành W2"]
    C --> D["Runtime nhận W2, RoleID"]
    D --> E["Spring Vault unwrap W2 -> S2"]
    E --> F["AppRole login -> client token T2"]
    F --> G["VaultTemplate đọc KV v2"]
    G --> H{"Token T2 còn hiệu lực?"}
    H -- "Có / renew được" --> G
    H -- "Cần login mới" --> I["Cấp credential mới trước khi re-auth"]
    I --> B
~~~

- **SecretID TTL:** tính từ lúc Vault phát SecretID, không phải từ lúc pod sẵn sàng.
- **SecretID use count:** giới hạn số lần SecretID được dùng để login, không giới hạn số lần đọc KV bằng client token.
- **Wrapping token TTL:** tính từ lúc response được bọc; thường ngắn hơn SecretID TTL và chỉ unwrap một lần.
- **Client token TTL:** bắt đầu sau AppRole login; token có thể được gia hạn trong giới hạn Vault nếu phù hợp.

Không giả định `LifecycleAwareSessionManager` tự cấp SecretID hoặc wrapping token mới. Nó có thể quản lý gia hạn **client token**; khi client token phải đăng nhập lại, cơ chế lấy credential vẫn phải dùng được.

## 3. Chọn mô hình cấp lại SecretID trước khi viết pipeline

| Chiến lược Spring Vault | Thành phần phát SecretID | Credential được inject | Khi instance cần login mới |
| --- | --- | --- | --- |
| `RoleId.provided + SecretId.provided` | Provisioner bên ngoài Java | RoleID + SecretID thật | Credential cũ có thể hết TTL/lượt; phải nạp SecretID mới nếu không còn hợp lệ |
| `RoleId.provided + SecretId.wrapped` | Provisioner bên ngoài Java | RoleID + wrapping token cho SecretID | Token bọc cũ đã unwrap; phải nhận wrapper mới |
| `RoleId.provided + SecretId.pull` | Chính ứng dụng với bootstrap Vault token | RoleID + bootstrap token | Có thể xin SecretID mới nếu bootstrap token còn hiệu lực/quyền |
| `RoleId.pull + SecretId.pull` | Chính ứng dụng với bootstrap Vault token | Bootstrap token + tên AppRole | Có thể lấy cả hai nếu bootstrap token đủ ACL, TTL/lượt |
| Workload auth khác (Kubernetes/IAM/OIDC) | Vault auth method phù hợp nền tảng | Danh tính workload | Có thể loại bỏ nhu cầu phân phối SecretID qua pipeline |

**Trọng tâm bài:** `provided RoleID + wrapped SecretID`. Thiết kế này tách được quyền **phát SecretID** khỏi Java workload: provisioner có ACL tạo credential; runtime chỉ nhận RoleID và một wrapping token ngắn hạn.

Không gọi `SecretId.provided(...)` là “Vault push mode” một cách máy móc. Với Vault, **pull mode** chỉ việc Vault tự sinh SecretID qua endpoint `secret-id`; **push mode** là bên ngoài đăng ký custom SecretID qua `custom-secret-id`. Ở Spring Vault, `provided` chỉ nghĩa là credential đã có sẵn khi cấu hình client.

**Tiêu chí chọn mô hình:** ứng dụng chạy bao lâu, có thể re-authenticate không cần restart không, broker có cấp credential mới lúc chạy không, bootstrap token có được phép xuất hiện trong JVM không và nền tảng có workload identity sẵn hay không.

## 4. Thiết lập Vault: role, policy và quyền provisioner

Phần thực hành tạo AppRole tên `report-worker` chỉ được đọc một secret giả trong KV v2.

### 4.1. Chuẩn bị môi trường lab

Giả sử Vault đã init/unseal và shell quản trị có token đủ quyền:

~~~bash
# Chỉ dùng HTTP cho local/dev.
export VAULT_ADDR="http://127.0.0.1:8200"

# Chỉ chạy nếu auth/approle chưa tồn tại:
vault auth enable approle

# Chỉ chạy nếu secret/ chưa là mount KV v2:
vault secrets enable -path=secret -version=2 kv

# Dữ liệu giả để test:
vault kv put secret/apps/report-worker status="ready"
~~~

Nếu mount đã có, hãy kiểm tra mount hiện hữu và bỏ qua lệnh enable trùng. Không chạy lệnh thay đổi role/policy trên Vault production khi đang làm lab.

### 4.2. Policy nghiệp vụ cho token của AppRole

Tạo file `report-worker-read.hcl`:

~~~hcl
path "secret/data/apps/report-worker" {
  capabilities = ["read"]
}
~~~

Đăng ký:

~~~bash
vault policy write report-worker-read report-worker-read.hcl
~~~

Với KV v2, URL API để đọc dữ liệu là `secret/data/apps/report-worker`, dù CLI dùng `vault kv get secret/apps/report-worker` và Spring Vault dùng logical path `apps/report-worker` dưới mount `secret`.

Không cấp `create`, `update`, `delete`, `list` tùy tiện cho workload chỉ cần đọc một secret.

### 4.3. AppRole có SecretID một lần dùng

~~~bash
vault write auth/approle/role/report-worker \
    bind_secret_id=true \
    token_policies="report-worker-read" \
    secret_id_ttl=10m \
    secret_id_num_uses=1 \
    token_ttl=30m \
    token_max_ttl=2h \
    token_type=service \
    token_num_uses=0

vault read auth/approle/role/report-worker
~~~

Các giới hạn mang ý nghĩa:

- `bind_secret_id=true`: một lần login cần RoleID và SecretID.
- `secret_id_ttl=10m`: SecretID mới có thời hạn giới hạn; với deploy xếp hàng lâu có thể hết hạn trước khi pod khởi động.
- `secret_id_num_uses=1`: SecretID mới chỉ dùng để login một lần. Không thích hợp để chia sẻ cho nhiều replica.
- `token_ttl=30m` / `token_max_ttl=2h`: vòng đời client token riêng, còn chịu giới hạn của Vault.
- `token_num_uses=0`: không giới hạn số request dùng client token bằng tham số này.
- `token_policies`: token workload chỉ đọc KV theo `report-worker-read`.

Đây là cấu hình **minh họa**. Một service dài hạn cần thiết kế renewal/re-authentication trước khi đặt SecretID một lần dùng. Nếu Vault cấp client token có trần TTL 2 giờ, một instance hoạt động nhiều giờ có thể cần đăng nhập lại; wrapper lúc startup **không thể unwrap lại**.

### 4.4. Policy tối thiểu cho provisioner

Tạo file `report-worker-provisioner.hcl` trên máy quản trị:

~~~hcl
# Đọc RoleID khi cần inject cho instance.
path "auth/approle/role/report-worker/role-id" {
  capabilities = ["read"]
}

# Phát SecretID mới cho instance.
path "auth/approle/role/report-worker/secret-id" {
  capabilities = ["update"]
}
~~~

Nạp policy:

~~~bash
vault policy write report-worker-provisioner \
    report-worker-provisioner.hcl
~~~

Token provisioner nên được cấp qua **danh tính pipeline/broker đã xác thực** và chỉ mang quyền cần thiết. Không dùng root token trong job thường xuyên, không gắn policy này vào AppRole client token của Java.

Nếu provisioner phải tra cứu/hủy SecretID bằng accessor, cần cấp riêng quyền tương ứng:

~~~hcl
path "auth/approle/role/report-worker/secret-id-accessor/lookup" {
  capabilities = ["update"]
}

path "auth/approle/role/report-worker/secret-id-accessor/destroy" {
  capabilities = ["update"]
}
~~~

Đừng thêm các quyền quản lý accessor nếu hệ thống phát credential không có nhiệm vụ thu hồi. Mọi quyền mở rộng phải dựa trên quy trình thực tế.

## 5. Cấp SecretID mới cho mỗi lần triển khai

### 5.1. Phát một SecretID bình thường

Endpoint Vault tạo SecretID mới:

~~~http
POST /v1/auth/approle/role/report-worker/secret-id
X-Vault-Token: <PROVISIONER_TOKEN>
Content-Type: application/json

{
  "ttl": "5m",
  "num_uses": 1
}
~~~

Response thông thường chứa `secret_id` và `secret_id_accessor`. Chúng **khác nhau**:

- `secret_id` là credential dùng cho `auth/approle/login` cùng RoleID.
- `secret_id_accessor` là định danh quản lý để lookup/destroy credential theo ACL thích hợp; **không thể dùng thay SecretID để login**.

Nếu cung cấp SecretID thô bằng kênh injection đáng tin cậy, ứng dụng dùng `SecretId.provided(secretId)`. Trong pipeline nhiều tầng, nên cân nhắc **response wrapping** để trung gian không cần giữ SecretID thô.

### 5.2. Cấp SecretID có response wrapping

Trong một phiên lab dùng token provisioner:

~~~bash
# Mỗi lần chạy tạo một SecretID MỚI và response wrapping token MỚI.
vault write -wrap-ttl=90s -f \
    auth/approle/role/report-worker/secret-id
~~~

Vault CLI hiển thị wrapping token, thời hạn và creation path thay vì hiển thị SecretID. Output minh họa:

~~~text
wrapping_token:               <WRAPPING_TOKEN_W2>
wrapping_token_ttl:           1m30s
wrapping_token_creation_path: auth/approle/role/report-worker/secret-id
~~~

**Production:** không để output chứa wrapping token trong CI logs. Provisioner nên gọi Vault qua API/TLS, giữ wrapping token trong secret broker hoặc kênh injection của orchestration và trao nó tới **đúng một instance**.

Tương đương về HTTP:

~~~http
POST /v1/auth/approle/role/report-worker/secret-id
X-Vault-Token: <PROVISIONER_TOKEN>
X-Vault-Wrap-TTL: 90s
Content-Type: application/json

{}
~~~

Header `X-Vault-Wrap-TTL` làm Vault bọc **response phát SecretID**. Dữ liệu trả về cho provisioner có `wrap_info.token`, `wrap_info.ttl` và `wrap_info.creation_path`, không chứa SecretID thô ở phần response thông thường.

### 5.3. Tránh nhầm lẫn về accessor trong response wrapping

Khi response được wrap, `secret_id_accessor` nằm trong **response gốc**, được trả sau thao tác unwrap. Provisioner **không mặc nhiên biết accessor chỉ từ `wrap_info`**. Vì vậy:

- Không giả định provisioner luôn có thể ghi `secret_id_accessor` khi vừa phát wrapper.
- Nếu quy trình phải hủy credential của một deploy cụ thể, hãy xây phương án tracking được cấp quyền: người nhận báo accessor qua control channel bảo mật, hoặc provisioner quản lý inventory/accessor theo quyền Vault, kết hợp metadata không nhạy cảm.
- Không unwrap token trong provisioner chỉ để lấy accessor rồi vẫn chuyển **cùng wrapping token** cho ứng dụng; token đó sẽ bị tiêu thụ.
- Với SecretID `num_uses=1`, khi login thành công credential đã hết lượt, việc truy vết/hủy SecretID có thể không còn là biện pháp thu hồi hữu ích; client token đã phát cần được xem xét **riêng**.

Dùng metadata như `deployment_id` hoặc `instance_id` giúp truy vết, nhưng **không chứa dữ liệu nhạy cảm** vì metadata SecretID có thể xuất hiện ở audit logs dưới dạng plaintext.

## 6. Quy trình triển khai an toàn theo từng instance

Giả sử công ty triển khai `report-worker:v2` vào Kubernetes hoặc một nền tảng container khác. Các bước quản trị nằm ở **control plane**, ứng dụng Java chỉ thực hiện login và thao tác nghiệp vụ.

~~~mermaid
sequenceDiagram
    autonumber
    participant CI as Pipeline / Deployment Controller
    participant P as Secret Provisioner
    participant Vault as HashiCorp Vault
    participant App as Java instance v2
    participant KV as KV v2
    CI->>P: Chuẩn bị instance v2 với deployment_id
    P->>Vault: Đọc RoleID theo quyền provisioner nếu cần
    P->>Vault: POST secret-id + X-Vault-Wrap-TTL
    Vault-->>P: wrap_info.token = W2
    P-->>CI: Chuyển W2 bằng kênh bí mật
    CI-->>App: Inject RoleID + W2 khi khởi động
    App->>Vault: sys/wrapping/unwrap (W2)
    Vault-->>App: SecretID S2; W2 không dùng lại được
    App->>Vault: auth/approle/login (RoleID, S2)
    Vault-->>App: client token T2 + policy + TTL
    App->>KV: GET dữ liệu bằng T2
    KV-->>App: Kết quả nếu được cấp quyền
    App-->>CI: Readiness PASS
    CI->>CI: Chuyển traffic sang v2
    CI->>CI: Drain/shutdown instance v1
~~~

**Trình tự vận hành gợi ý:**

1. **Tạo deployment identity:** hệ thống quản lý một `deployment_id`/`instance_id` không chứa secret. Mỗi replica mới là một lần bootstrap riêng.
2. **Chuẩn bị role và policy** bằng IaC trước khi rollout; không dùng pipeline ứng dụng để tự tạo policy rộng tùy ý.
3. **Provisioning đúng thời điểm:** chỉ phát wrapper khi biết instance sắp khởi động để TTL không trôi mất trong queue dài.
4. **Inject đúng một người nhận:** RoleID và wrapping token được chuyển qua secret broker/runtime injection có quyền đọc giới hạn; không dùng ConfigMap công khai, build args hay logs.
5. **Kiểm tra provenance (nếu thiết kế yêu cầu):** xác minh `creation_path` của wrapping token đúng endpoint cấp SecretID trước khi unwrap.
6. **Khởi động Java:** Spring Vault unwrap và login. Instance chỉ được coi là ready sau khi xác thực truy cập Vault và các dependency thiết yếu đúng.
7. **Chuyển traffic:** với rolling update hoặc blue-green, giữ instance cũ cho tới khi instance mới thực sự sẵn sàng.
8. **Thu hồi và vệ sinh:** sau khi kết thúc phiên cũ, xử lý client token/secret theo chính sách vòng đời; xóa quyền truy cập tới secret injection của instance cũ.

Không cấp wrapper cho **một Deployment object dùng chung** nếu nhiều replica sẽ cùng đọc và unwrap một giá trị. Response wrapping token **chỉ được dùng một lần**, nên mỗi replica phải có token bọc riêng.

### 6.1. Vì sao nên cấp lúc instance sắp khởi động?

Giả sử:

~~~text
10:00:00   Pipeline phát SecretID S2 và wrapper W2 (TTL wrapper = 90 giây)
10:00:15   Image pull bắt đầu
10:01:40   Node mới được scheduler cấp
10:01:50   Java bắt đầu unwrap W2
~~~

Trong timeline này `W2` đã hết 90 giây trước khi Java kịp unwrap. SecretID `S2` có thể vẫn còn TTL 10 phút, nhưng ứng dụng **không thể lấy response bị bọc** bằng `W2` đã hết hạn.

Giải pháp không phải đặt `secret_id_num_uses=0`, vì đó là giới hạn **số lần login**, không kéo dài TTL wrapper. Các lựa chọn hợp lý là phát wrapper sát lúc khởi động, giảm queue delay bằng warm capacity hoặc điều chỉnh wrapping TTL dựa trên thống kê độ trễ thực và chính sách bảo mật.

### 6.2. Kiểm tra creation path trước unwrap

Một token bọc hợp lệ không tự chứng minh nó chứa SecretID của đúng role. Có thể tra metadata qua API:

~~~http
POST /v1/sys/wrapping/lookup
Content-Type: application/json

{
  "token": "<WRAPPING_TOKEN_W2>"
}
~~~

Kết quả phải có `creation_path` chính xác là:

~~~text
auth/approle/role/report-worker/secret-id
~~~

`lookup` không tiêu thụ wrapper; `unwrap` mới làm token một lần dùng bị tiêu thụ. Thực hiện lookup qua Vault server có TLS tin cậy và policy phù hợp; không lưu token thật vào log.

Trong ví dụ Spring Vault trực tiếp, `SecretId.wrapped(...)` sẽ tự unwrap, **không mặc định bảo đảm tất cả bước kiểm tra provenance của quy trình cấp phát**. Nếu bắt buộc kiểm tra trước, đặt một lớp bootstrap có kiểm soát ở phía runtime/provisioner để xác minh rồi mới giao wrapper còn nguyên vẹn cho Spring Vault.

## 7. Spring Vault Java: nhận SecretID bọc riêng cho lần deploy mới

### 7.1. Cấu hình `ClientAuthentication`

Một ứng dụng Spring Vault Core có thể nhận RoleID và **wrapping token mới** qua biến môi trường hoặc secret file mount được cấp cho **instance đó**:

~~~java
package example.vault;

import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AppRoleAuthentication;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.RoleId;
import org.springframework.vault.authentication.AppRoleAuthenticationOptions.SecretId;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.VaultToken;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class ReportWorkerVaultConfiguration
        extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        // Production phải dùng HTTPS với CA/truststore đúng.
        return VaultEndpoint.from(URI.create(requiredEnv("VAULT_ADDR")));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        String roleId = requiredEnv("VAULT_ROLE_ID");
        String wrappingToken =
                requiredEnv("VAULT_SECRET_ID_WRAPPING_TOKEN");

        AppRoleAuthenticationOptions options =
                AppRoleAuthenticationOptions.builder()
                        .path("approle")
                        .roleId(RoleId.provided(roleId))
                        .secretId(SecretId.wrapped(
                                VaultToken.of(wrappingToken)))
                        .build();

        return new AppRoleAuthentication(options, vaultClient());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required runtime configuration: " + name);
        }
        return value;
    }
}
~~~

Giải thích:

- `.path("approle")` là mount auth method; nếu Vault mount ở `auth/team-approle` thì dùng `.path("team-approle")`.
- `RoleId.provided(...)` nhận RoleID đã được cấp; nó không gọi endpoint `role-id`.
- `SecretId.wrapped(VaultToken.of(wrappingToken))` nhận token bọc chưa dùng. Spring Vault thực hiện unwrap để lấy SecretID rồi mới login.
- `AppRoleAuthentication` là `ClientAuthentication`. Sau login, `SessionManager` giữ/renew client token theo khả năng của token và cấu hình Spring Vault.
- Constructor `new AppRoleAuthentication(options, vaultClient())` phù hợp Spring Vault 4.1.x. Với các phiên bản cũ, API có thể dùng `RestOperations` hoặc `RestClient`; cần kiểm tra version dependency.

**Bảo mật:** không ghi RoleID, wrapping token, SecretID sau unwrap hay client token vào log. Hàm `requiredEnv` cố ý chỉ nêu **tên cấu hình thiếu**, không in giá trị. Dù biến môi trường dễ trình diễn, secret file mount hoặc broker phù hợp với chính sách nền tảng có thể an toàn hơn khi triển khai thực tế.

### 7.2. Đọc KV v2 qua `VaultTemplate`

~~~java
package example.vault;

import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class ReportWorkerSecrets {

    private final VaultTemplate vaultTemplate;

    public ReportWorkerSecrets(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String deploymentStatus() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("apps/report-worker");

        if (response == null) {
            throw new IllegalStateException("Vault secret not found");
        }
        Map<String, Object> data = response.getRequiredData();
        Object status = data.get("status");

        if (!(status instanceof String value)) {
            throw new IllegalStateException(
                    "Vault field 'status' missing or invalid");
        }
        return value;
    }
}
~~~

Với Vault lab đã ghi `status="ready"`, phương thức trả `ready` nếu login và policy đúng. Logical path Java là `apps/report-worker` dưới mount `secret`; ACL đọc KV v2 là `secret/data/apps/report-worker`.

Không đánh đồng **Spring Context khởi động xong** với **AppRole xác thực thành công**. Tùy bean và thời điểm `VaultTemplate` được dùng, login có thể xảy ra khi request đầu tiên cần token. Nếu readiness phụ thuộc Vault, hãy đặt một phép kiểm tra chủ động, có giới hạn timeout và không làm lộ secret nghiệp vụ.

### 7.3. Nếu nền tảng cấp SecretID trực tiếp

Trong môi trường có secret broker inject SecretID thô vào runtime một cách tin cậy, chỉ cần thay phần options:

~~~java
AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.provided(requiredEnv("VAULT_SECRET_ID")))
                .build();
~~~

**Không nhầm:** SecretID được cấp trực tiếp vẫn phải là credential **mới/còn hạn** cho phiên deploy đó. `SecretId.provided(...)` không tự xin SecretID mới và cũng không tự xoay vòng chuỗi mà bean đã nạp.

### 7.4. Nếu Java được phép tự xin SecretID mới

Một lựa chọn khác là cấp bootstrap Vault token hẹp cho Java:

~~~java
VaultToken bootstrapToken = VaultToken.of(
        requiredEnv("VAULT_APPROLE_BOOTSTRAP_TOKEN"));

AppRoleAuthenticationOptions options =
        AppRoleAuthenticationOptions.builder()
                .path("approle")
                .appRole("report-worker")
                .roleId(RoleId.provided(requiredEnv("VAULT_ROLE_ID")))
                .secretId(SecretId.pull(bootstrapToken))
                .build();
~~~

Khi đó bootstrap token phải có quyền `update` trên `auth/approle/role/report-worker/secret-id`. Ứng dụng có thể xin SecretID mới khi login **nếu bootstrap token còn TTL/quyền và số lượt sử dụng**. Đổi lại, bootstrap token có quyền phát credential là một **bí mật mạnh** phải được bảo vệ, không phải cách loại bỏ toàn bộ rủi ro credential.

Với workload đã có danh tính Kubernetes/Cloud IAM đáng tin cậy, cân nhắc dùng auth method gốc thay vì cấp một bootstrap token lâu dài chỉ để tạo AppRole SecretID.

## 8. Rolling update, blue-green và rollback

### 8.1. Rolling deployment không làm mất phiên cũ quá sớm

Một chiến lược triển khai zero-downtime nên làm như sau:

~~~text
Trạng thái ban đầu:
    v1: pod A (T1), pod B (T2) đang phục vụ

Rollout:
    1. Controller tạo pod C (v2)
    2. Provisioner phát SecretID S3, wrapper W3 cho C
    3. Pod C unwrap W3 và AppRole login -> T3
    4. Readiness C xác nhận API Vault và dependency quan trọng
    5. Chuyển một phần traffic sang C
    6. Drain pod A; sau đó tiếp tục tạo pod D với S4/W4 riêng
    7. Drain pod B khi D sẵn sàng

Không thực hiện:
    Chia sẻ W3 cho pod C và D
    Tắt A và B trước khi C xác thực thành công
~~~

Từng instance có **SecretID riêng**. RoleID vẫn có thể giống nhau vì tất cả instance thuộc cùng AppRole, nhưng client token của từng instance được Vault phát riêng.

Nếu không thể tạo secret injection per-pod trong cơ chế hiện tại, đừng nhét một wrapping token dùng một lần vào một cấu hình Deployment mà mọi replica cùng đọc. Cần điều chỉnh kiến trúc broker/sidecar/controller trước khi triển khai quy mô lớn.

### 8.2. Blue-green: hai môi trường cùng tồn tại

Với `blue` đang phục vụ và `green` chuẩn bị nhận traffic:

- `blue` giữ token đã được cấp theo vòng đời của nó.
- Mỗi instance `green` nhận SecretID mới; xác minh readiness từ đúng mạng egress.
- Chỉ chuyển traffic sau khi `green` hoạt động ổn định.
- Nếu `green` thất bại, rollback traffic về `blue` **không cần tái sử dụng** wrapper của `green`.
- Khi ngừng `blue`, xử lý token và secret injection còn tồn tại theo quy trình bảo mật.

Giữ các phiên cũ trong khoảng chuyển tiếp làm tăng số client token đang tồn tại, nhưng đó là một phần cần tính đến của rollout có kiểm soát. Giám sát token/lease và giới hạn nguồn tài nguyên tương ứng.

### 8.3. Rollback image phải nhận credential mới

Ví dụ `v2` có lỗi và pipeline chạy lại image `v1` dưới dạng **instance E mới**. Dù mã nguồn quay về phiên bản cũ:

~~~text
Không đúng:
    rollback v2 -> v1
    dùng lại W1 từ lần deploy v1 trước

Đúng:
    rollback v2 -> v1
    provisioner phát S5 và W5 mới cho instance E
    E unwrap W5, AppRole login và kiểm chứng readiness
~~~

Wrapping token `W1` đã được dùng hoặc quá TTL; SecretID `S1` có thể đã hết lượt/hạn. **Credential gắn với vòng đời instance, không gắn với tag image.**

### 8.4. Retry pipeline: tránh tạo lại một giả định sai

Một job deploy có thể bị retry vì lỗi scheduling, network hoặc health check. Không mặc định rằng “cùng deployment_id” có nghĩa “cùng wrapping token còn dùng được”.

Khi retry:

1. Xác định instance cũ đã chạy và token có thể đã bị unwrap hay chưa.
2. Nếu không thể chắc chắn token còn nguyên vẹn, **không retry unwrap vô hạn**.
3. Với một instance bootstrap mới, provisioner phát **SecretID mới + wrapping token mới**; không thu hồi nhầm token phục vụ traffic đang hoạt động.
4. Dùng record điều khiển không nhạy cảm như `deployment_id`, `instance_id`, `issue_time` và trạng thái giao nhận để đối chiếu; credential phải ở secret store riêng.
5. Cấp token/SecretID theo quota hợp lý và theo dõi số lần phát để tránh pipeline lỗi phát credential không giới hạn.

Vault không bảo đảm API phát SecretID idempotent theo một `deployment_id` do bạn tự đặt. Mỗi lần gọi endpoint `secret-id` có thể tạo một credential mới; **idempotency của pipeline là trách nhiệm của control plane**.

## 9. Thu hồi, accessor và sự khác biệt với client token

### 9.1. Có nên destroy SecretID cũ ngay khi v2 ready?

Không có một đáp án chung cho mọi kiến trúc:

- Với `secret_id_num_uses=1`, SecretID có thể đã hết lượt ngay sau login; hủy SecretID không thay thế việc quản lý client token đã phát.
- Với `secret_id_num_uses>1`, SecretID cũ còn lượt có thể cho phép login mới nếu chưa thu hồi. Sau khi chắc chắn instance cũ không cần re-auth, nên xử lý/revoke theo chính sách rotation.
- Trong rolling update, **không thu hồi nhầm token hiện đang được instance cũ dùng để phục vụ traffic** trước khi drain xong.
- Nếu có sự cố lộ SecretID, đánh giá các AppRole client token đã cấp; **destroy SecretID không tự revoke token đó**.

Một quy trình có thể giữ thời gian overlap giới hạn để tránh downtime rồi thu hồi credential cũ. Thời gian overlap phải được quyết định cùng nhu cầu availability và rủi ro bảo mật.

### 9.2. Destroy SecretID qua accessor

Nếu provisioner hoặc hệ thống inventory được cấp quyền có `secret_id_accessor` của credential cần thu hồi:

~~~bash
vault write auth/approle/role/report-worker/secret-id-accessor/destroy \
    secret_id_accessor="<ACCESSOR_LAB>"
~~~

Endpoint có thể chặn các lần AppRole login **mới** bằng SecretID đó. Accessor không phải SecretID, và không thể dùng thay SecretID trong login. Nếu provisioner chỉ nhận response wrapping, hãy nhớ accessor có thể nằm trong nội dung được bọc; việc tra cứu accessor đòi hỏi một quy trình quản lý có quyền hợp lệ, **không được hủy bừa các credential khác của cùng role**.

### 9.3. Đối với client token đã cấp

Sau khi ứng dụng login, Vault trả một **client token** có TTL và policies. Token đó có thể tiếp tục hoạt động sau khi SecretID hết lượt/hết hạn. Khi cần dừng ngay một instance bị xâm nhập, phải đánh giá **token revocation** theo khả năng xác định token của instance, session manager, audit và token hierarchy.

Không khuyến nghị revoke tất cả token của AppRole chỉ vì một instance deploy lỗi, trừ khi đang ứng phó sự cố và phạm vi ảnh hưởng được chấp nhận. Một thao tác revoke quá rộng có thể làm gián đoạn các replica hợp lệ.

## 10. Vòng đời dài hạn và giới hạn của `SecretId.wrapped(...)`

### 10.1. Startup thành công chưa bảo đảm chạy ổn nhiều ngày

Với role minh họa:

~~~text
SecretID S2:    ttl=10m, num_uses=1
Wrapping W2:    ttl=90s, unwrap một lần
Client token T2: ttl ban đầu 30m, trần renewal phụ thuộc role/Vault
~~~

Nếu Java login thành công lúc 10:00, wrapping token `W2` không còn dùng được sau đó; SecretID `S2` cũng đã dùng hết lượt. `T2` có thể vẫn hợp lệ và được renew khi Vault cho phép. Khi `T2` cần được thay bằng token mới sau giới hạn renewal hoặc revoke, ứng dụng **không thể tự unzip/unwrap `W2` lần nữa**.

Vì thế, `SecretId.wrapped(VaultToken.of(...))` với biến môi trường tĩnh chỉ giải quyết **bootstrap lần đầu**. Nó không phải một cơ chế cấp SecretID mới liên tục cho JVM dài hạn.

### 10.2. Ba hướng thiết kế cho service chạy lâu

| Hướng | Lợi ích | Điều kiện |
| --- | --- | --- |
| **Restart có điều phối kèm wrapper mới** | Đơn giản; mỗi instance đi qua một bootstrap mới | Controller phải cấp credential mới theo instance trước khi token buộc login lại |
| **Secret broker có API rotation/refresh** | Có thể lấy credential mới lúc JVM đang chạy | Cần cách tái tạo `ClientAuthentication`/session hoặc một provider tương thích, kiểm thử race/failure |
| **Pull/workload identity** | Có thể xin credential/token mới không cần wrapper cũ | Bootstrap identity/token phải được quản lý và có khả năng refresh; ACL tối thiểu |

Không chỉ sửa biến môi trường hoặc secret mount rồi kỳ vọng `AppRoleAuthenticationOptions` đã tạo tự nạp giá trị mới. Tùy kiến trúc, cần tái khởi tạo bean/client/session hoặc dùng một cơ chế auth khác được thiết kế cho rotation lâu dài.

### 10.3. Khi nào nên tránh AppRole wrapping qua CI?

Nếu service có hàng trăm replica được tạo liên tục, startup queue dài, tự hồi phục nhiều lần hoặc có workload identity Kubernetes/cloud sẵn, mô hình provisioner phát wrapper qua CI cho từng replica có thể khó vận hành. Lúc đó nên đánh giá:

- Kubernetes Auth, IAM/OIDC/cloud auth trực tiếp với Vault.
- Vault Agent hoặc broker có cơ chế auth và cấp token theo workload.
- Cách cấp quyền KV, Transit, PKI theo chính sách mà không phải quản lý SecretID thủ công.

Mục tiêu không phải dùng AppRole bằng mọi giá, mà là **đảm bảo danh tính workload được cấp quyền đúng và có thể phục hồi khi credential/token hết hạn**.

## 11. Những lỗi phổ biến trong quá trình triển khai lại

| Triệu chứng | Điểm lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- | --- |
| Pod v2 khởi động, báo lỗi unwrap | `sys/wrapping/unwrap` | Wrapper đã dùng/TTL hết hoặc giao nhầm instance | Cấp SecretID và wrapper mới, kiểm tra thời gian pipeline |
| Pod thứ nhất chạy, các pod sau lỗi | Phân phối | Nhiều replica cùng nhận một wrapping token | Cấp token bọc riêng từng instance |
| Unwrap xong nhưng login 403 | `auth/approle/login` | SecretID không thuộc role, hết TTL/lượt, ràng buộc CIDR sai | Kiểm tra role, egress IP, thời gian phát và quota |
| Deploy v1 chạy được, rollback v1 mới lại lỗi | Bootstrap | Dùng lại wrapper/SecretID của phiên triển khai trước | Coi rollback là một deploy mới về mặt credential |
| CI retry liên tục tạo nhiều SecretID | Provisioner | Không có kiểm soát retry/quota/idempotency ở control plane | Theo dõi issue events và giới hạn phát theo instance |
| Pipeline log chứa wrapping token | CI/secret injection | Command output hoặc debug/tracing không được che | Vô hiệu log bí mật, rotate credential có nguy cơ lộ |
| Java chạy ban đầu, vài giờ sau không đọc được KV | Token lifecycle | Client token hết TTL/trần renewal, wrapper cũ không thể dùng lại | Xây refresh/redeploy hoặc auth strategy phù hợp |
| Login thành công nhưng KV trả 403 | Authorization | `token_policies` thiếu `read` hoặc sai API path KV v2 | Kiểm tra policy `secret/data/apps/report-worker` |
| Wrapper creation path sai | Provenance | Bên cấp phát nhầm role/endpoint hoặc token bọc không mong đợi | Từ chối wrapper trước unwrap, rà soát broker |
| Mất kết nối sau khi gửi unwrap | Network/race | Vault có thể đã tiêu thụ wrapper nhưng Java không nhận được response | Không retry mù; kiểm tra audit/lookup và cấp wrapper mới |
| Wrapper hết TTL khi chờ node | Scheduling | Phát credential quá sớm hoặc TTL không đủ | Dời bước phát sát startup, đo latency và điều chỉnh TTL |
| Thu hồi SecretID mà client token vẫn dùng được | Token lifecycle | SecretID và client token có vòng đời độc lập | Revoke token liên quan khi cần, tránh revoke quá rộng |
| Deployment green ready nhưng dữ liệu sai | Readiness/test | Chỉ kiểm tra process up, chưa kiểm tra quyền và secret path | Thêm phép kiểm tra Vault nghiệp vụ đã giới hạn |

### 11.1. Chẩn đoán theo endpoint

~~~text
POST auth/approle/role/report-worker/secret-id
    -> lỗi provisioner, ACL, role, Vault API

POST sys/wrapping/lookup hoặc POST sys/wrapping/unwrap
    -> lỗi wrapper, TTL, nguồn gốc, dùng một lần, mạng

POST auth/approle/login
    -> lỗi RoleID/SecretID, TTL/uses, CIDR, auth mount

GET secret/data/apps/report-worker
    -> lỗi client token, token-bound CIDR, policy, KV v2 path
~~~

Từng request cần cơ chế telemetry khác nhau. Không ghi SecretID, wrapping token, bootstrap token, RoleID hoặc client token vào log, tracing span hay metric label. Dùng correlation ID không nhạy cảm và Vault audit logs được giới hạn quyền.

### 11.2. Retry cần phân biệt trạng thái trước và sau unwrap

- **Chưa gửi unwrap:** nếu wrapper còn TTL và đúng người nhận, có thể dùng một lần như dự kiến.
- **Đã unwrap thành công:** wrapper không thể dùng lại. Nếu login thất bại, cần cấp credential phù hợp cho lần login kế tiếp.
- **Timeout không rõ đã unwrap hay chưa:** không giả định wrapper còn nguyên. Tra cứu/audit theo quy trình, cấp credential mới cho instance bootstrap mới nếu cần.
- **AppRole login thành công nhưng readiness fail do KV policy:** sửa policy/path/secret; không cần tạo lại wrapper chỉ vì lỗi ACL nếu phiên client token hiện có vẫn hợp lệ.

## 12. Bảo mật pipeline và trách nhiệm các thành phần

### 12.1. Tách quyền

| Thành phần | Có quyền gì? | Không nên có quyền gì? |
| --- | --- | --- |
| **Vault admin/IaC** | Tạo policy, mount, role, điều chỉnh TTL/CIDR | Chạy trực tiếp trong JVM workload |
| **Provisioner** | Tạo SecretID theo đúng role, đọc RoleID nếu cần | Đọc toàn bộ KV nghiệp vụ hoặc quản lý mọi role |
| **Deployment controller** | Phân phối wrapping token cho đúng instance | In credential vào logs, nhúng trong image |
| **Java workload** | Unwrap và login bằng RoleID/SecretID, dùng client token đọc KV | Tạo SecretID/đổi role nếu mô hình là wrapped |
| **Security/audit** | Xem metadata, audit logs và revoke theo phạm vi được cấp | Truy cập SecretID thô không cần thiết |

### 12.2. Những yếu tố phải được đánh giá

- **Kênh vận chuyển:** HTTPS/TLS giữa các thành phần; Vault listener và CA tin cậy.
- **Nơi lưu:** secret injection hoặc broker; không dùng image layers, Git, chat, dashboard công khai hoặc pipeline artifacts.
- **Thời hạn:** wrapping TTL đủ cho độ trễ startup và ngắn theo rủi ro; SecretID TTL/số lượt phù hợp với login thực tế.
- **Danh tính recipient:** wrapper chỉ cấp cho một instance; không tái sử dụng trong autoscaling.
- **Mạng:** nếu role/SecretID/token có bound CIDRs, phải dùng địa chỉ egress mà Vault **thật sự nhìn thấy**.
- **Audit:** ghi số lần cấp/unwrap/login/revoke theo môi trường/deployment ID không nhạy cảm; theo dõi bất thường.
- **Hủy bỏ:** ai có quyền revoke token/credential khi instance mất kiểm soát? Có inventory nào đáng tin cậy không?
- **Thay đổi version:** rollback image cũng cần credential mới; không dùng token bọc từ lịch sử pipeline.

## 13. Kiểm thử tích hợp và acceptance checklist

Thử trên Vault dev/test riêng, có thể dùng Testcontainers Vault. Mỗi trường hợp có **credential mới** để không phụ thuộc thứ tự test hoặc vô tình dùng hết `secret_id_num_uses`.

| Ca kiểm thử | Chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| **Fresh redeploy** | Deploy v1 rồi v2, cấp wrapper riêng | Cả hai instance có thể login và đọc KV trước khi v1 được drain |
| **Không tái sử dụng wrapper** | Dùng lại W1 ở pod mới | Unwrap thất bại; phải phát W2 |
| **Không chia sẻ replica** | Hai instance thử dùng cùng W | Chỉ một instance unwrap thành công; thiết kế phải cấp W riêng |
| **TTL wrapper quá ngắn** | Chờ quá TTL trước startup | Không unwrap; pipeline báo lỗi cấp phát, không tự dùng SecretID cũ |
| **SecretID TTL hết trước login** | Wrapper còn dùng được nhưng SecretID đã quá TTL trong setup test | Unwrap không bảo đảm login thành công |
| **SecretID một lần dùng** | `num_uses=1` và cùng SecretID thử login hai lần | Lần thứ hai bị từ chối dù token đầu có thể còn hiệu lực |
| **Provenance** | Wrapper được phát từ endpoint khác | Bootstrap checker từ chối dựa trên `creation_path` |
| **Provisioner thiếu ACL** | Token provisioner không có `update` secret-id | Không phát được credential mới |
| **Token đúng, KV sai policy** | Role token không có `read` | Login thành công, `VaultTemplate` nhận 403 |
| **Rollback về v1** | Tạo instance v1 mới sau khi dừng v2 | Instance nhận SecretID/wrapper mới, không dùng lại W1 |
| **Unwrap timeout/unknown outcome** | Mô phỏng lỗi mạng sau request | Không lặp unwrap vô hạn; control plane cấp credential mới có kiểm soát |
| **Client token hết hạn** | Trần TTL ngắn và instance chạy lâu | Phát hiện re-auth không thành công nếu chỉ có wrapper cũ; có phương án khắc phục |
| **Draining cũ đúng cách** | Rolling update với readiness bắt buộc | Chỉ tắt v1 sau khi v2 login + đọc KV thành công |
| **Secret leakage guard** | Bật log CI/test có kiểm soát | Không xuất hiện token/SecretID trong output, artifact hoặc metric label |

### 13.1. Ví dụ Spring integration test

~~~java
package example.vault;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

// Chỉ chạy với Vault test và wrapper MỚI cho mỗi execution.
// Vault AppRole, policy, KV v2 đã được provision trước test.
@SpringBootTest
class ReportWorkerSecretsIT {

    @Autowired
    ReportWorkerSecrets secrets;

    @Test
    void readsKvAfterFreshDeploymentAuthentication() {
        assertEquals("ready", secrets.deploymentStatus());
    }
}
~~~

Đây là **bài test tích hợp phác thảo**, không phải một lớp test tự chạy độc lập nếu chưa provision Vault, Spring Boot test dependency và biến môi trường. Nếu dùng Spring Framework thuần, thay `@SpringBootTest` bằng cấu hình Spring Test phù hợp.

**Không thể xác minh tính đúng của redeploy chỉ bằng `assertNotNull(builder.build())`.** Test phải dùng Vault thật hoặc Vault test container, phát wrapper mới, thực hiện login và kiểm tra quyền trên path KV v2.

### 13.2. Bài tập thực hành

**Bài tập 1 — Lần triển khai mới.** Tạo role `report-worker`, policy chỉ đọc một KV v2 path và `secret_id_num_uses=1`. Cấp một wrapper W1 cho instance v1, sau đó W2 cho v2. Tại sao cùng RoleID nhưng không nên dùng cùng wrapper?

**Bài tập 2 — Redeploy chậm.** Wrapping TTL 90 giây, queue của orchestrator đôi khi lên tới 3 phút. Bạn thay đổi thứ tự cấp credential hay tăng TTL? Đưa ra phương án dựa trên đo latency và kiểm soát rủi ro.

**Bài tập 3 — Rollback.** Image v2 lỗi nên trở lại v1. Hãy trình bày thứ tự rollback có readiness và chứng minh wrapper W1 cũ không được tái dùng.

**Bài tập 4 — Thu hồi có phạm vi.** Một instance cũ bị nghi lộ SecretID; client token của nó còn TTL. Vì sao destroy SecretID chưa đủ? Cần xác định token/session nào trước khi thu hồi?

**Bài tập 5 — Service dài hạn.** Client token có giới hạn renewal, trong khi SecretID đã dùng hết lượt và wrapper đã unwrap. Đề xuất một trong ba phương án: restart có wrapper mới, broker refresh hoặc phương thức auth theo workload; nêu trade-off vận hành.

**Bài tập 6 — CI retries.** Pipeline tạo wrapper W1 rồi bị timeout khi inject. Job retry bằng cùng deployment_id. Vì sao không được mặc định W1 chưa được unwrap? Thiết kế trạng thái control plane và giới hạn số lần phát như thế nào?

### 13.3. Tiêu chí hoàn thành

Người học có thể tự giải thích và triển khai chuỗi **provisioner tạo SecretID mới → response wrapping → inject cho instance mới → unwrap → AppRole login → VaultTemplate đọc KV**, phân biệt được credential của các phiên deploy/replica, cấu hình ACL tối thiểu, kiểm thử restart/rollback, và xác định đúng giải pháp cho re-authentication lâu dài.

## Tài liệu tham khảo

- [Spring Vault Reference — AppRole authentication và token lifecycle](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault API — AppRoleAuthentication](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthentication.html)
- [Spring Vault API — AppRoleAuthenticationOptions.SecretId](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AppRoleAuthenticationOptions.SecretId.html)
- [Spring Vault Reference — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [HashiCorp Vault — AppRole HTTP API (SecretID và accessor)](https://developer.hashicorp.com/vault/api-docs/auth/approle)
- [HashiCorp Vault — AppRole best practices](https://developer.hashicorp.com/vault/docs/auth/approle/approle-pattern)
- [HashiCorp Vault — Response wrapping](https://developer.hashicorp.com/vault/docs/concepts/response-wrapping)
- [HashiCorp Vault — Wrapping lookup API](https://developer.hashicorp.com/vault/api-docs/system/wrapping-lookup)
- [HashiCorp Vault — Tokens, TTL và renewal](https://developer.hashicorp.com/vault/docs/concepts/tokens)
