# Xác thực workload Kubernetes theo ServiceAccount

Trong chương **Thực hành tổng hợp** của module **SPRING_VAULT**, chúng ta xây dựng một luồng xác thực **workload Kubernetes → HashiCorp Vault → Spring Vault → KV v2**. Mục tiêu là cho ứng dụng Java đọc một cấu hình bí mật mà **không hardcode Vault token**, không đưa AppRole SecretID vào image và không cấp cho Pod quyền quản trị Vault.

Kubernetes cung cấp **ServiceAccount (SA)** để định danh workload. Kubelet có thể gắn vào Pod một **ServiceAccount JSON Web Token (JWT)** có thời hạn và audience cụ thể. Vault **Kubernetes auth method** nhận JWT cùng tên role, xác minh token qua Kubernetes **TokenReview API**, so khớp tên ServiceAccount, namespace và audience, sau đó phát hành **Vault token** với các ACL policies đã gắn cho role. Spring Vault sử dụng Vault token đó khi gọi `VaultOperations`/`VaultTemplate` để đọc KV secrets, Transit encryption hoặc PKI theo những quyền được cấp.

Bài lab này dùng:

| Thành phần | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| Kubernetes namespace của workload | `orders-lab` | Cô lập workload thử nghiệm |
| ServiceAccount của ứng dụng | `orders-api` | Danh tính Kubernetes của Pod |
| Vault Kubernetes auth mount | `kubernetes/` | Endpoint đăng nhập `auth/kubernetes/login` |
| Vault auth role | `orders-api` | Chỉ cho phép SA `orders-api` trong `orders-lab` |
| JWT audience | `vault` | Token được phát hành với mục đích xác thực vào Vault |
| Vault ACL policy | `orders-kv-ro` | Chỉ đọc `secret/data/orders/config` |
| KV secrets engine | `secret/`, phiên bản KV v2 | Lưu cấu hình của ứng dụng |
| Logic KV path | `orders/config` | Path truyền cho Spring Vault `opsForKeyValue` |
| JWT file trong Pod | `/var/run/secrets/vault/token` | Projected SA token được đọc lại khi login |

Giá trị secret trong bài chỉ là **dữ liệu giả**: `DEMO_ONLY_NOT_A_REAL_SECRET`. Người vận hành phải thay host, namespace, ServiceAccount và chính sách TLS cho môi trường thật. Không sao chép lệnh có quyền quản trị lên cluster dùng chung khi chưa có quy trình phê duyệt.

## 1. Mục tiêu đầu ra và tiêu chí hoàn thành

Hoàn thành lab nghĩa là bạn chứng minh được **đúng danh tính đăng nhập**, **đúng phạm vi quyền** và **ứng dụng thực sự dùng token do Vault cấp**, không chỉ việc Pod đã được tạo.

1. Pod `orders-api` được gán `serviceAccountName: orders-api` trong namespace `orders-lab`.
2. Kubelet cung cấp một JWT ngắn hạn với `aud=vault` tại file được ứng dụng đọc; ứng dụng không ghi JWT ra log.
3. Vault có auth mount `kubernetes/`, có thể gọi Kubernetes TokenReview bằng danh tính reviewer phù hợp.
4. Vault role `orders-api` chỉ chấp nhận `orders-lab/orders-api` và `audience=vault`.
5. Spring Vault đọc JWT từ file, gửi `POST /v1/auth/kubernetes/login`, nhận Vault token, dùng policy `orders-kv-ro` để đọc KV v2.
6. Thử JWT không đúng ServiceAccount, namespace hoặc audience đều bị từ chối; thử đọc path KV khác cũng bị chặn.
7. Khi JWT được kubelet thay mới và ứng dụng cần **re-login**, nó sử dụng token mới từ file thay vì cố định JWT tại startup.

Hai danh tính có vòng đời khác nhau: **ServiceAccount JWT** chỉ là bằng chứng danh tính do Kubernetes phát hành; **Vault token** là credential riêng được Vault phát hành sau khi xác thực. Không đồng nhất hai chuỗi hoặc giả định một token hết hạn thì token kia cũng lập tức bị thu hồi.

## 2. Luồng tin cậy giữa Kubernetes, Vault và Spring Vault

~~~mermaid
sequenceDiagram
    participant K as Kubernetes kubelet
    participant P as Spring Boot Pod orders-api
    participant V as Vault Kubernetes auth
    participant A as Kubernetes API / TokenReview
    participant KV as Vault KV v2
    K->>P: Mount projected JWT (SA=orders-api, ns=orders-lab, aud=vault)
    P->>P: Đọc JWT từ file
    P->>V: POST /auth/kubernetes/login {role, jwt}
    V->>A: TokenReview với reviewer credential
    A-->>V: authenticated + SA identity / audience
    V->>V: So role binding + tạo Vault token/policies
    V-->>P: Vault token (TTL, policies)
    P->>KV: GET /secret/data/orders/config với Vault token
    KV-->>P: data.data.apiKey
~~~

### Ai xác thực ai?

| Ranh giới | Bằng chứng / quyền | Điều gì được kiểm tra? |
| --- | --- | --- |
| Pod → Kubernetes | ServiceAccount gắn vào Pod | Kubernetes cấp token đúng ServiceAccount |
| Pod → Vault | JWT của Pod + tên Vault role | Auth method sử dụng TokenReview, role kiểm tra tên SA/namespace/audience |
| Vault → Kubernetes API | Reviewer JWT có quyền TokenReview | Kubernetes xác nhận JWT workload còn hợp lệ |
| Vault → Pod | Vault token chứa policies/TTL | Pod dùng token để gọi API Vault, không dùng SA JWT thay thế |
| Pod → KV | ACL policy trên Vault token | `read` đúng `secret/data/orders/config` |

**Kubernetes RBAC không cấp quyền đọc Vault secret.** Kubernetes RBAC xác định ai được thao tác với Kubernetes API. Vault ACL quyết định token có thể đọc KV, dùng Transit, PKI hay không. ServiceAccount có quyền tạo Deployment trong Kubernetes vẫn **không đương nhiên** có quyền ở Vault.

Ngược lại, reviewer có quyền TokenReview **không được** trao cho SA `orders-api` chỉ để ứng dụng login. Quyền đó thuộc thành phần Vault hoặc một danh tính reviewer chuyên trách.

## 3. Điều kiện môi trường và giới hạn lab

Lab giả định:

- Một Kubernetes cluster có thể dùng projected ServiceAccount tokens; namespace `vault` có Vault server chạy **bên trong cùng cluster**. Trong phần reviewer mặc định, ví dụ giả định Vault **1.9.3 hoặc mới hơn** để đọc lại local reviewer JWT khi token được xoay vòng.
- Vault đã khởi tạo/unseal, truy cập bằng HTTPS, có operator token hợp lệ cho việc bật auth, thiết lập role/policy và KV. Không dùng operator token trong application Pod.
- Vault server có ServiceAccount tên `vault` ở namespace `vault`, có **mount token/CA mặc định** và kết nối được tới Kubernetes API. Tên này chỉ là ví dụ: phải đối chiếu ServiceAccount thực mà Vault Deployment/StatefulSet sử dụng.
- `vault.vault.svc` là DNS ví dụ của Vault Service; chứng thư TLS của Vault phải hợp lệ cho hostname mà app dùng. Môi trường khác cần dùng host và CA trust tương ứng.
- Người học có `kubectl` truy cập cluster và Vault CLI được cấu hình đúng `VAULT_ADDR`/namespace/operator credentials.

Không bật auth method lần hai nếu `kubernetes/` đã được cấu hình trong môi trường dùng chung. **Chạy các bước quản trị trong môi trường lab độc lập** hoặc áp dụng bằng IaC đã review.

### Hai phương án triển khai cần phân biệt

1. **Vault server chạy trong Kubernetes:** có thể dùng *local reviewer ServiceAccount JWT* và CA certificate của Pod Vault. Đây là phương án lab được minh họa.
2. **Vault server chạy ngoài Kubernetes:** không có local token/CA của Pod Vault. Operator phải cấu hình `kubernetes_host`, `kubernetes_ca_cert` và phương án `token_reviewer_jwt` được quản lý/luân chuyển hoặc mô hình reviewer bằng JWT của client với RBAC khác. Không copy cấu hình “chỉ có kubernetes_host” rồi kỳ vọng TokenReview tự hoạt động từ một Vault server nằm ngoài cluster.

Vault **Kubernetes auth** sử dụng TokenReview. Nếu thay bằng Vault **JWT auth** xác minh chữ ký qua OIDC/JWKS, các endpoint, role và mô hình thu hồi token khác; đó là kiến trúc riêng, không phải thay tên mount đơn thuần.

## 4. Tạo namespace và ServiceAccount của workload

Chuẩn bị namespace và SA độc lập với tài khoản mặc định:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders-lab
automountServiceAccountToken: false
~~~

Giải thích: cấu hình `automountServiceAccountToken: false` ở đây nhằm **không tự động mount JWT mặc định**. Ở bước Deployment chúng ta cung cấp một **projected token riêng với audience `vault`**. Nếu bạn chọn dùng token mặc định thay vì custom projection, cần bật automount và thiết lập Vault role `audience` **khớp với `aud` thật của token đó**; không giả định audience mặc định luôn là `vault`.

Áp dụng manifest trong lab:

~~~bash
kubectl apply -f orders-serviceaccount.yaml
kubectl get serviceaccount orders-api -n orders-lab
~~~

Đây là tên file **minh họa** cho manifest đã lưu bằng công cụ vận hành của bạn, không phải file được bài học tự tạo. Không chạy `kubectl get secret` rồi in token của ServiceAccount ra terminal chỉ để xác minh SA tồn tại.

### Projected ServiceAccount token và vòng đời

Kubernetes hiện đại hỗ trợ TokenRequest và projected ServiceAccount tokens. Token được gắn với Pod/ServiceAccount, có `aud` và `exp`; kubelet có thể cập nhật nội dung file trước khi hết hạn. Khi Pod/ServiceAccount bị xóa hoặc JWT hết hạn, token không còn dùng để đăng nhập mới như trước.

- **JWT audience** nói token được phát cho dịch vụ nào. Trong lab, `aud=vault`, không dùng chung token này để gọi Kubernetes API server.
- **JWT expiration** là thời gian sống danh tính Kubernetes, không phải TTL của Vault token sau login.
- **Projected volume** không phải một Kubernetes Secret kiểu legacy long-lived token; tránh tạo token lâu dài chỉ để đơn giản hóa lab.
- Nếu tắt automount nhưng quên cấu hình projected volume, Spring Vault sẽ báo không thể đọc JWT file.
- Ngay cả khi JWT bị thu hồi, **Vault token đã phát hành** có thể còn tồn tại cho đến khi TTL/revocation của Vault xử lý; cần thiết kế TTL và cleanup độc lập.

## 5. Cấp quyền TokenReview cho danh tính của Vault

Kubernetes auth phải gọi `TokenReview API` để kiểm tra JWT của workload. Nếu Vault chạy trong namespace `vault` với ServiceAccount `vault`, gắn `system:auth-delegator` cho **chính danh tính đó**, không gắn cho `orders-api`:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: vault-server-tokenreview-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator
subjects:
  - kind: ServiceAccount
    name: vault
    namespace: vault
~~~

Nếu Vault đang dùng reviewer service account khác, thay `subjects` cho đúng tài khoản thực sự được Vault sử dụng. `ClusterRoleBinding` có phạm vi cấp cluster và cần quyền quản trị Kubernetes để tạo. Đừng cấp `system:auth-delegator` cho mọi workload hoặc ServiceAccount mặc định.

~~~bash
kubectl apply -f vault-reviewer-binding.yaml

# Chỉ kiểm tra quyền của reviewer, không đọc token.
kubectl auth can-i create tokenreviews.authentication.k8s.io \
  --as=system:serviceaccount:vault:vault
~~~

Lệnh `kubectl auth can-i --as` có thể yêu cầu quyền impersonate của người vận hành; nếu không có quyền đó, sử dụng phương án kiểm thử RBAC được cluster administrator phê duyệt. Kết quả `yes` chỉ xác minh RBAC, **không chứng minh** đường mạng, CA trust và TokenReview request thực sự hoạt động.

**Điều kiện quan trọng:** Vault server phải có local ServiceAccount token được mount và phương thức Kubernetes auth phải đọc được nó. Khi Vault 1.9.3+ chạy trong Pod theo thiết lập hỗ trợ, để trống `token_reviewer_jwt` và `kubernetes_ca_cert` thì auth method có thể dùng local token và local CA. Nếu Pod Vault tắt automount hoặc không có mount tương ứng, phải cấu hình nguồn reviewer/CA khác một cách chủ động.

## 6. Bật và cấu hình Vault Kubernetes auth

Đây là thao tác **operator**, không phải code Spring Boot. Ví dụ lệnh chạy trong lab có Vault CLI đã được xác thực:

~~~bash
# Bật auth method khi mount này chưa tồn tại.
vault auth enable -path=kubernetes kubernetes

# Vault server nằm trong cùng cluster và có local SA token/CA.
# Kubernetes API Service ở đây là địa chỉ ví dụ thường dùng.
vault write auth/kubernetes/config \
  kubernetes_host="https://kubernetes.default.svc:443" \
  disable_iss_validation=true

vault read auth/kubernetes/config
~~~

Ở Vault Kubernetes auth hiện đại, `disable_iss_validation=true` thường là mặc định mới và được khuyến nghị: chính Kubernetes TokenReview cũng kiểm tra tính hợp lệ issuer. Mount tạo từ Vault đời cũ có thể giữ cấu hình cũ, nên đọc lại giá trị khi nâng cấp Kubernetes 1.21+.

`token_reviewer_jwt` và `kubernetes_ca_cert` **không được ghi vào lệnh trên** vì lab giả định Vault server đã có token reviewer và CA qua local Pod volume. Nếu Vault chạy ngoài cluster hoặc dùng reviewer được quản lý riêng, phải cung cấp CA và reviewer JWT theo tài liệu chính thức. Tránh nhúng token reviewer ngắn hạn vào giá trị cấu hình tĩnh rồi quên việc xoay vòng.

### Hợp đồng endpoint Kubernetes auth

| Mục đích | HTTP method | Vault API path | Actor |
| --- | --- | --- | --- |
| Bật auth method | `POST` | `/v1/sys/auth/kubernetes` | Vault operator |
| Cấu hình TokenReview | `POST` | `/v1/auth/kubernetes/config` | Vault operator |
| Cấu hình role | `POST` | `/v1/auth/kubernetes/role/orders-api` | Vault operator |
| Login từ ứng dụng | `POST` | `/v1/auth/kubernetes/login` | Spring Vault workload |
| Đọc KV v2 | `GET` | `/v1/secret/data/orders/config` | Vault token có policy `read` |

Trong request login chỉ có `role` và `jwt`. **Không cần Vault token trước khi login**; nếu phải có Vault token mới gọi được login thì mô hình bootstrap đã bị thiết kế sai. Sau login, Vault trả `auth.client_token`, `auth.lease_duration`, `auth.renewable` và các metadata khác. Không ghi raw response login vào log vì chứa credential.

~~~json
{
  "role": "orders-api",
  "jwt": "<PROJECTED_SERVICE_ACCOUNT_JWT>"
}
~~~

Body phía trên chỉ minh họa hợp đồng. Giá trị trong dấu ngoặc là placeholder, **không phải JWT dùng được**; chương trình Spring Vault sẽ đọc token từ file chứ không đưa chuỗi đó vào source.

## 7. Tạo policy chỉ đọc KV v2

Thực hành một bản ghi giả để kiểm tra quyền:

~~~bash
# Chỉ tạo mount KV mới trong lab; không ghi đè engine đang tồn tại.
vault secrets enable -path=secret -version=2 kv

vault kv put -mount=secret orders/config \
  apiKey="DEMO_ONLY_NOT_A_REAL_SECRET"
~~~

KV v2 có đường HTTP `secret/data/orders/config` dù logical path khi dùng Vault CLI/Spring Vault API mức cao là `orders/config`. Vault ACL phải đặt trên **đường HTTP**, không phải chỉ `secret/orders/config`:

~~~hcl
# Policy orders-kv-ro: chỉ cho phép đọc một tài liệu KV v2.
path "secret/data/orders/config" {
  capabilities = ["read"]
}
~~~

Ghi policy từ file HCL đã được review:

~~~bash
vault policy write orders-kv-ro orders-kv-ro.hcl
vault policy read orders-kv-ro
~~~

Tài liệu không cấp `list` cho `secret/metadata/*`, không cấp quyền ghi/xóa KV, không cấp quyền tạo Transit keys hay quản trị PKI. Nếu bài lab mở rộng sang Transit encryption hoặc PKI, phải tạo các policy riêng theo endpoint và lý do nghiệp vụ, thay vì cấp wildcard rộng cho toàn `secret/*` hoặc `auth/*`.

## 8. Gắn ServiceAccount với một Vault role

Role kiểm tra ràng buộc danh tính của JWT rồi quyết định policies và TTL của **Vault token** được cấp:

~~~bash
vault write auth/kubernetes/role/orders-api \
  bound_service_account_names="orders-api" \
  bound_service_account_namespaces="orders-lab" \
  audience="vault" \
  token_policies="orders-kv-ro" \
  token_ttl="30m" \
  token_max_ttl="2h" \
  token_type="service"

vault read auth/kubernetes/role/orders-api
~~~

| Field | Giá trị lab | Ý nghĩa |
| --- | --- | --- |
| `bound_service_account_names` | `orders-api` | Chỉ ServiceAccount được nêu tên |
| `bound_service_account_namespaces` | `orders-lab` | Chỉ namespace được nêu tên |
| `audience` | `vault` | JWT bắt buộc có audience tương ứng |
| `token_policies` | `orders-kv-ro` | Vault token chỉ có quyền được policy cho phép, cộng những policy mặc định còn áp dụng |
| `token_ttl` | `30m` | TTL cấp ban đầu, vẫn chịu giới hạn mount/global |
| `token_max_ttl` | `2h` | Giới hạn TTL theo role; phải thiết kế renew/re-login |
| `token_type` | `service` | Phù hợp ví dụ dùng session manager có thể gia hạn/revoke |

**Không dùng** `bound_service_account_names="*"` hoặc `bound_service_account_namespaces="*"` để “cho đăng nhập nhanh” trong production. Một role có wildcard có thể cho Pod khác yêu cầu token với policy của đơn vị khác. Cần namespace riêng, SA riêng và role riêng cho từng trust boundary.

Giá trị `token_type=batch` có thể phù hợp một số workload ngắn hạn nhưng có semantics renewal/revocation khác service token. Không đổi token type trong lab này khi còn muốn kiểm tra Spring Vault session renewal.

### Role name không phải tên Pod

`role=orders-api` là tên Vault auth role. `ServiceAccount=orders-api` là danh tính Kubernetes được cấp token. Chúng **có thể trùng tên như trong bài**, nhưng không bắt buộc; điều Vault kiểm tra là ràng buộc `bound_service_account_names` và `bound_service_account_namespaces`. Một Pod tên `orders-api-6bc...` không cần trùng tên với role hay ServiceAccount.

### Dùng namespace selector?

Vault có tùy chọn `bound_service_account_namespace_selector` cho Kubernetes namespace labels. Đây là tính năng đặc biệt và có thể làm điều kiện namespace được ghép theo logic **OR** với danh sách namespace trực tiếp. Khi mới học, chỉ bind danh sách namespace cụ thể như ví dụ để tránh mở phạm vi truy cập ngoài ý muốn.

## 9. Triển khai Pod với projected JWT có audience riêng

Ví dụ Deployment tối giản dưới đây chạy ứng dụng demo Java đã đóng gói image. **Image là địa chỉ giả**; hãy thay bằng image đã build từ ứng dụng của bạn. Manifest chỉ minh họa phần identity và volume, chưa bao gồm Service, resources, probes, NetworkPolicy, JVM truststore và cấu hình bảo mật production.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.invalid/orders-api-lab:1.0
          env:
            - name: VAULT_ADDR
              value: "https://vault.vault.svc:8200"
          volumeMounts:
            - name: vault-jwt
              mountPath: /var/run/secrets/vault
              readOnly: true
      volumes:
        - name: vault-jwt
          projected:
            sources:
              - serviceAccountToken:
                  path: token
                  audience: vault
                  expirationSeconds: 3600
~~~

Điểm kiểm tra:

1. `serviceAccountName` quyết định **danh tính**, không phải label của Pod.
2. `automountServiceAccountToken: false` vô hiệu mount JWT mặc định; volume `projected` cung cấp token riêng.
3. `audience: vault` phải đúng với `audience="vault"` trong Vault role.
4. `expirationSeconds: 3600` là thời hạn yêu cầu cho **ServiceAccount JWT**, không phải TTL Vault token `30m`. Kubernetes có thể điều chỉnh thời hạn thực được cấp.
5. `/var/run/secrets/vault/token` là đường **trong container**. Phải khớp đường Spring Vault JWT supplier sẽ đọc.
6. App container phải đọc được file token. Với Pod chạy UID/GID hạn chế, cấu hình permission/securityContext/projected volume cho đúng và xác minh tại runtime; đừng sửa permission thành world-writable.
7. App cần mạng HTTPS tới Vault; **Vault cần mạng HTTPS tới Kubernetes API**. Đây là hai đường kết nối khác nhau.

Không thêm JWT làm environment variable hoặc Kubernetes ConfigMap/Secret để cố định giá trị: projected file cho phép kubelet xoay vòng token. Không log token hoặc dùng `kubectl exec ... cat /var/run/secrets/vault/token` trong tài liệu công khai.

## 10. Cấu hình Spring Vault theo ServiceAccount

Spring Vault cung cấp `KubernetesAuthentication` và `KubernetesAuthenticationOptions`. Mặc định options có thể lấy JWT từ `/var/run/secrets/kubernetes.io/serviceaccount/token` **mỗi lần login**. Do lab này dùng custom projected path, ta truyền `jwtSupplier` để **đọc lại file ở mỗi lần cần đăng nhập**, không giữ JWT cố định trong một field tại startup.

Đoạn Java sau minh họa **Spring Vault 4.1+**, nơi `KubernetesAuthentication` có constructor nhận `VaultClient`. Với Spring Vault đời cũ, constructor có thể nhận `RestOperations`/`RestClient`; cần đối chiếu Javadoc theo dependency của dự án trước khi copy:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.KubernetesAuthentication;
import org.springframework.vault.authentication.KubernetesAuthenticationOptions;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

@Configuration
public class VaultKubernetesConfig extends AbstractVaultConfiguration {

    private static final Path JWT_FILE =
            Path.of("/var/run/secrets/vault/token");

    @Override
    public VaultEndpoint vaultEndpoint() {
        // Chỉ dùng URL đã được operator cấu hình/kiểm soát.
        return VaultEndpoint.from("https://vault.vault.svc:8200");
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        KubernetesAuthenticationOptions options =
                KubernetesAuthenticationOptions.builder()
                        .role("orders-api")
                        .path("kubernetes")
                        .jwtSupplier(() -> {
                            try {
                                // Đọc token MỚI khi re-login, không cache
                                // raw JWT từ lần khởi động đầu tiên.
                                String jwt = Files.readString(
                                        JWT_FILE, StandardCharsets.UTF_8);
                                if (jwt.isBlank()) {
                                    throw new IllegalStateException(
                                            "ServiceAccount JWT file rỗng");
                                }
                                return jwt.strip();
                            } catch (IOException e) {
                                throw new UncheckedIOException(
                                        "Không đọc được ServiceAccount JWT", e);
                            }
                        })
                        .build();

        // Constructor VaultClient xuất hiện từ Spring Vault 4.1.
        return new KubernetesAuthentication(options, vaultClient());
    }
}
~~~

**Lưu ý triển khai:** Đoạn mã dùng `VaultEndpoint.from(...)` để minh họa một endpoint cố định trong lab. Ở production, lấy endpoint từ cấu hình được kiểm soát, không hardcode môi trường; bảo đảm CA trust và hostname verification đầy đủ. Với CA nội bộ, cấu hình JVM truststore hoặc HTTP client SSL trust thích hợp, **không tắt xác minh TLS**.

Ở ứng dụng Spring Boot dùng Spring Cloud Vault, có thể chọn auto-configuration Kubernetes auth qua properties thay vì định nghĩa `AbstractVaultConfiguration` bằng tay. **Không đồng thời bật hai cách cấu hình Vault client và hai session managers độc lập** nếu không chủ đích; kiểm tra dependency và autoconfiguration của dự án.

### Vì sao `jwtSupplier` quan trọng?

Token projection có thể được kubelet thay thế khi JWT sắp hết hạn. Nếu tại startup ta gọi `Files.readString(...)` một lần rồi lưu vào `String` vĩnh viễn, lúc Vault session cần **re-login** bằng JWT cũ thì Vault/Kubernetes có thể từ chối vì `exp` đã qua. Supplier ở ví dụ đọc file mỗi lần login, cho phép lấy token đang được kubelet cập nhật.

Tuy vậy, bản thân supplier **không tự ép Vault token phải re-login**: đó là trách nhiệm session lifecycle. Cấu hình `LifecycleAwareSessionManager` (nếu được dùng) xử lý thời hạn/renew/re-login của **Vault token** theo quy tắc Spring Vault và kiểu token trả về; các lỗi network, role và JWT vẫn cần monitoring.

### Đọc KV v2 bằng VaultOperations

Khi bean `VaultOperations` đã được cấu hình với `ClientAuthentication` và session, business service đọc đúng logical path:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersConfigurationReader {

    private final VaultKeyValueOperations kv;

    public OrdersConfigurationReader(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String requiredApiKey() {
        VaultResponse response = kv.get("orders/config");
        if (response == null) {
            throw new IllegalStateException("Thiếu KV cấu hình bắt buộc");
        }

        Map<String, Object> values = response.getRequiredData();
        Object raw = values.get("apiKey");
        if (!(raw instanceof String key) || key.isBlank()) {
            throw new IllegalStateException("Thiếu trường apiKey");
        }
        return key; // Không ghi key vào log, metrics hoặc HTTP response.
    }
}
~~~

`opsForKeyValue("secret", KV_2).get("orders/config")` tự xử lý cấu trúc KV v2; không truyền `secret/data/orders/config` nguyên vẹn vào `get(...)` của API này. Còn ACL Vault dùng `secret/data/orders/config` vì policy áp dụng **HTTP API path**.

Ứng dụng có thể gọi `requiredApiKey()` lúc startup để **fail fast** nếu Vault auth/secret không sẵn sàng hoặc theo một chính sách refresh có kiểm soát. Không log secret, Vault token, JWT, HTTP body đăng nhập hay toàn bộ response KV khi ứng dụng báo lỗi.

## 11. Kiểm thử end-to-end: cho phép đúng danh tính, từ chối sai danh tính

### Kiểm tra cấu hình trước khi chạy

~~~bash
# Không in thông tin nhạy cảm; chỉ kiểm tra metadata cho lab.
kubectl get sa orders-api -n orders-lab
kubectl get clusterrolebinding vault-server-tokenreview-lab

vault auth list
vault read auth/kubernetes/config
vault read auth/kubernetes/role/orders-api
vault policy read orders-kv-ro
vault kv get -mount=secret orders/config
~~~

Ở môi trường thật, kết quả `vault kv get` chứa secret và có thể bị lưu trong terminal logs. Trong lab chỉ dùng giá trị giả; nếu là secret thật, tránh in giá trị và dùng công cụ kiểm tra metadata/kết quả đọc an toàn.

Triển khai ứng dụng lab:

~~~bash
kubectl apply -f orders-deployment.yaml
kubectl rollout status deploy/orders-api -n orders-lab
kubectl get pods -n orders-lab -l app=orders-api
~~~

Trong ứng dụng demo, có thể dùng một `ApplicationRunner` gọi `requiredApiKey()` lúc startup và chỉ ghi marker không chứa secret khi thành công:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class VaultLabStartupCheck {

    private static final Logger log =
            LoggerFactory.getLogger(VaultLabStartupCheck.class);

    @Bean
    ApplicationRunner vaultSecretReady(OrdersConfigurationReader reader) {
        return args -> {
            reader.requiredApiKey();
            log.info("VAULT_CONFIG_READY"); // Không log apiKey/JWT.
        };
    }
}
~~~

Với đoạn này, Pod có thể khởi động thất bại nếu auth, network, TLS hoặc secret không hợp lệ. Đây là hành vi **cố ý fail fast cho lab**; ở production, cần thiết kế readiness, retry có deadline và chính sách startup cho phù hợp với khả năng phục hồi.

### Những thử nghiệm bắt buộc

| Trường hợp | Thay đổi trong lab | Kết quả mong đợi |
| --- | --- | --- |
| **Positive path** | SA `orders-api`, ns `orders-lab`, aud `vault`, policy chính xác | Login thành công; business code đọc `apiKey` giả |
| SA name sai | Pod dùng SA `orders-other` nhưng role `orders-api` | TokenReview có thể xác nhận JWT hợp lệ, nhưng Vault role **từ chối login** |
| Namespace sai | Cùng tên SA `orders-api` ở namespace khác | Vault role từ chối login |
| Audience sai | JWT `aud` khác `vault` trong Vault role | Vault role/TokenReview từ chối JWT |
| Token đã hết hạn | Sử dụng JWT test hết hạn, không dùng projected token mới | Login mới bị từ chối |
| Reviewer thiếu RBAC | Thu hồi binding **trên cluster lab riêng** | Vault không gọi được TokenReview; login thất bại |
| Pod thiếu JWT file | Tắt projection và automount | JWT supplier lỗi file, không login được |
| Policy thiếu `read` | Role cấp policy không có `secret/data/orders/config` | **Login có thể thành công** nhưng KV GET bị `403` |
| Đọc sai KV path | Gọi `orders/private` ngoài quyền | Bị từ chối theo ACL hoặc 404 theo state/path |
| Token rotate | Kubelet thay JWT và Spring Vault cần re-login | Supplier đọc nội dung JWT hiện tại, không dùng bản startup đã quá hạn |
| Vault ngừng sẵn sàng | Simulate network timeout/503 | App có lỗi được phân loại, retry hữu hạn; không lộ token |

Khi kiểm thử negative path, không sửa/xóa Vault reviewer binding hoặc role trên cluster production. Dùng namespace, mount và test instance riêng; sau thử nghiệm phải khôi phục cấu hình đã duyệt.

### Phân biệt lỗi TokenReview và lỗi ACL

Nếu Pod nhận `403 permission denied` lúc đọc `secret/data/orders/config`, **không kết luận JWT login thất bại** ngay. Có hai bước riêng:

1. **Login:** `POST /auth/kubernetes/login` kiểm tra SA JWT và role; Vault trả Vault token.
2. **Authorization:** `GET /secret/data/orders/config` kiểm tra Vault ACL của **Vault token**; có thể trả 403 dù login thành công.

Tương tự, nếu Vault không liên lạc được Kubernetes API/TokenReview vì thiếu RBAC hoặc CA, login thất bại **trước khi** ứng dụng có token để đọc KV. Đặt log/error code theo operation (`K8S_VAULT_LOGIN` khác `KV_ORDERS_CONFIG_READ`) để xác định đúng tầng lỗi.

## 12. Chẩn đoán sự cố theo triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra an toàn |
| --- | --- | --- |
| `NoSuchFileException` đọc JWT | Sai path, quên projected volume, mount chưa sẵn sàng | Kiểm tra manifest và sự tồn tại/quyền file, **không in nội dung JWT** |
| `403` tại `auth/kubernetes/login` | SA/name/ns/audience không khớp, JWT hết hạn | Đọc role và cấu hình Pod, xem audit metadata đã redacted |
| TokenReview `forbidden` ở phía Vault | Reviewer không có quyền `create tokenreviews` | Kiểm tra reviewer SA và ClusterRoleBinding |
| Vault không gọi được Kubernetes API | `kubernetes_host` sai, DNS/network policy, TLS CA mismatch | Kiểm tra kết nối Vault → API server và CA trust |
| Vault auth mount `404` | App dùng sai mount, ví dụ `auth/k8s/login` thay vì `auth/kubernetes/login` | So sánh `vault auth list` với `KubernetesAuthenticationOptions.path` |
| Login thành công nhưng KV `403` | `token_policies` hoặc KV v2 ACL sai | Kiểm tra `secret/data/orders/config`, policy, Vault namespace |
| KV `404` | Chưa tạo KV v2, nhầm mount hay path logic | Kiểm tra KV engine version và record của lab |
| Vài giờ sau login mới thất bại | Supplier cache JWT cũ, token file không rotate, reviewer JWT hết hạn | Kiểm tra cơ chế reread JWT và TokenReview reviewer lifecycle |
| Token/Vault lease tăng theo số Pod | Nhiều replica tạo session riêng, hoặc App + Agent cùng login | Theo dõi số Pod, auth logins, Vault token/lease metrics |
| `SSLHandshakeException` | App không tin Vault CA/hostname, hoặc Vault không tin Kubernetes CA | Xác định **hướng kết nối** bị lỗi trước khi sửa truststore |

### Ba đường mạng cần kiểm tra riêng

1. **Kubelet/Kubernetes → Pod:** cung cấp projected ServiceAccount token.
2. **App Pod → Vault HTTPS:** đăng nhập và đọc KV; cần DNS, NetworkPolicy, Vault TLS CA, endpoint.
3. **Vault → Kubernetes API HTTPS:** TokenReview; cần reviewer token, RBAC, CA và network route.

Đường (2) hoạt động không chứng minh đường (3) hoạt động. Một network policy chỉ cho Pod app tới Vault nhưng chặn Vault ra Kubernetes API sẽ gây lỗi login dù endpoint Vault phản hồi HTTP.

## 13. Token và lease khi Pod restart, rollout hoặc bị xóa

Đừng nhầm các vòng đời:

| Tài nguyên | Ai phát hành/quản lý? | Hết hiệu lực theo |
| --- | --- | --- |
| ServiceAccount JWT | Kubernetes API/kubelet | `exp`, audience, Pod/SA binding, token rotation |
| Vault token sau login | Vault auth/token subsystem, Spring Vault session manager | Vault TTL/max TTL, renew, revoke, re-login |
| Dynamic DB credential lease | Vault database engine và expiration manager | Lease TTL/renew/revoke; có thể phụ thuộc Vault token |
| KV v2 secret | Vault KV engine | Version/write/delete, không theo SA JWT TTL |
| PKI certificate | Vault PKI CA | X.509 `NotAfter`, revoke/rotation riêng |

Khi Pod bị xóa, projected JWT của Pod sẽ không còn là bằng chứng đăng nhập mới hợp lệ; nhưng **Vault token đã được cấp không nhất thiết bị hủy tức thời** chỉ vì Pod đã mất. Vì vậy cần `token_ttl`/`token_max_ttl` hợp lý, lifecycle cleanup của Spring Vault/Agent và monitoring token/lease.

Khi triển khai rolling update:

- Mỗi JVM/Pod mới có thể thực hiện login riêng; số Vault tokens có thể tăng tạm thời trong thời gian overlap.
- Một `LifecycleAwareSessionManager` được tái sử dụng trong cùng process giúp tránh login cho mỗi request; không tạo `VaultTemplate`/session manager tùy tiện ở mỗi lần gọi HTTP.
- Vault Agent sidecar nếu cũng auto-auth có thể tạo **token khác** ngoài Spring Vault. Xác định app trực tiếp gọi Vault hay chỉ đọc file Agent để tránh hai cơ chế lấy credential cùng chức năng.
- Các secret động từ database hay PKI có thể có lease/certificate lifetime riêng; kết quả login thành công không bảo đảm credential được renew hoặc hot-reload tự động.

Khi test, quan sát token renew và **re-login** riêng. Re-login đọc JWT mới từ file là yêu cầu quan trọng khi projected ServiceAccount token có thời hạn.

## 14. Bảo mật và khả năng quan sát

**Nguyên tắc quyền tối thiểu trong lab:**

- Kubernetes ServiceAccount `orders-api` chỉ phục vụ danh tính workload; không cấp `system:auth-delegator` hoặc quyền đọc Kubernetes Secrets toàn namespace nếu không cần.
- Vault Kubernetes role chỉ bind `orders-lab/orders-api`, đúng audience `vault`, TTL hữu hạn và policy `orders-kv-ro`.
- Vault operator và reviewer ServiceAccount là danh tính **khác ứng dụng**. Không đặt operator Vault token hoặc reviewer JWT vào Pod orders.
- Vault policy chỉ cho đọc `secret/data/orders/config`; mở rộng Transit/PKI bằng policy riêng theo endpoint, không cấp `sudo` hoặc `sys/auth/*` cho business app.
- Dùng HTTPS với CA/hostname verification ở cả hai đường App → Vault và Vault → Kubernetes API.
- Không log JWT, `auth.client_token`, token accessor, response secret, raw header `X-Vault-Token`, SecretID hoặc private key.

Những tín hiệu nên theo dõi:

| Tín hiệu | Nơi ghi nhận | Giúp phát hiện |
| --- | --- | --- |
| Login success/failure theo mount/role | Vault audit/metrics (đã redacted) | Role/audience/RBAC hoặc TokenReview lỗi |
| `403` ở endpoint KV | Spring Vault client/metrics | ACL thiếu quyền, path/namespace sai |
| Token renew/re-login events | Spring Vault session manager/instrumentation | JWT stale hoặc token lifecycle bất thường |
| Pod restarts/readiness | Kubernetes | App không login hoặc không đọc được secret |
| Vault HTTP latency/5xx/429 | Vault và ứng dụng | Tắc nghẽn, quota hoặc sự cố kết nối |
| Vault token/lease counts | Vault telemetry | Scale nhiều replica, token/lease còn tồn sau rollout |

Không gắn token/JWT/secret value hoặc Pod UID có cardinality cao vào Prometheus labels. Có thể dùng các operation ID cố định như `K8S_VAULT_LOGIN`, `ORDERS_CONFIG_READ`; luôn kiểm tra chính sách redaction đối với exception message và tracing attributes.

## 15. Mở rộng lab sang Transit và PKI

Sau khi login Kubernetes thành công, ứng dụng có thể gọi **Transit** hoặc **PKI** mà không thay đổi danh tính Kubernetes. Nhưng mọi endpoint yêu cầu **Vault policy riêng**:

| Nhu cầu | Vault endpoint ví dụ | ACL thông thường cần xem xét |
| --- | --- | --- |
| Đọc KV v2 | `secret/data/orders/config` | `read` |
| Transit encrypt | `transit/encrypt/orders-key` | `update` |
| Transit decrypt | `transit/decrypt/orders-key` | `update`, chỉ cấp khi thật sự cần giải mã |
| PKI issue certificate | `pki/issue/orders-server` | `update`, role PKI kiểm soát DNS/SAN/TTL |

Đừng dùng một policy wildcard cho mọi endpoint chỉ vì JWT login đã được chấp nhận. **Authentication xác minh danh tính, authorization giới hạn việc danh tính đó được làm.** Khi cấp Transit/PKI, cần kiểm tra vòng đời khóa/chứng thư, xử lý lỗi, giám sát và test khả năng không lộ plaintext/private key đúng với engine đó.

## 16. Checklist nghiệm thu

- [ ] Namespace `orders-lab` và ServiceAccount `orders-api` tồn tại đúng cluster.
- [ ] Vault reviewer ServiceAccount thực được bind quyền TokenReview; app SA không có quyền đó.
- [ ] Vault auth mount `kubernetes/` được cấu hình `kubernetes_host`/CA/reviewer đúng nơi Vault chạy.
- [ ] Role `orders-api` bind chính xác tên SA, namespace, `audience=vault` và token TTL/policy.
- [ ] App Pod có projected JWT `aud=vault` và đọc đúng file; JWT không bị cache cố định.
- [ ] Vault API endpoint/CA trust của Spring client đúng, TLS hostname verification được bật.
- [ ] Đã tạo KV v2 `secret/`, policy `orders-kv-ro` chỉ đọc `secret/data/orders/config`.
- [ ] Spring Vault dùng `KubernetesAuthentication`, lấy Vault token và đọc `orders/config` thành công.
- [ ] Test sai ServiceAccount, namespace, audience, hết hạn JWT và thiếu reviewer RBAC đều bị từ chối.
- [ ] Test login thành công nhưng thiếu KV policy có lỗi riêng, không nhầm với auth failure.
- [ ] Đã kiểm thử re-login sau khi kubelet xoay vòng JWT, Pod restart và scale-up.
- [ ] Logs/traces/metrics không chứa JWT, Vault token, secret value hoặc raw response lỗi.
- [ ] Toàn bộ thành phần lab được cô lập; không xóa hoặc sửa auth mount/role dùng chung production.

## 17. Ghi nhớ và tự kiểm tra

**ServiceAccount là danh tính của Pod trong Kubernetes; JWT là bằng chứng danh tính dùng để yêu cầu đăng nhập; Vault Kubernetes auth dùng TokenReview và role binding để phát hành Vault token; policy trên Vault token quyết định quyền với KV, Transit, PKI.** Bốn bước này phải được xác minh riêng. JWT audience, mount path, ServiceAccount name/namespace, reviewer RBAC và KV v2 policy là những điểm hợp đồng quan trọng nhất.

Hãy tự trả lời:

1. Vì sao `serviceAccountName` trong Deployment quan trọng hơn tên Pod khi Vault kiểm tra `bound_service_account_names`?
2. Điểm khác nhau giữa JWT do Kubernetes cấp và Vault token do `auth/kubernetes/login` trả về là gì?
3. Tại sao cần reviewer có quyền `create tokenreviews`, và vì sao không trao quyền đó cho SA ứng dụng?
4. Nếu Vault role yêu cầu `audience=vault` nhưng projected token có `aud=kubernetes.default.svc`, sẽ xảy ra chuyện gì?
5. Vì sao Spring Vault phải **đọc lại** projected JWT mỗi lần cần re-login thay vì cache JWT lúc startup?
6. Login thành công nhưng đọc `secret/data/orders/config` bị 403: cần kiểm tra thành phần nào?
7. Khi `automountServiceAccountToken=false`, cách nào giúp Pod vẫn có JWT phù hợp cho Vault?
8. Tại sao xóa Pod không đảm bảo mọi Vault token và database lease được thu hồi ngay lập tức?
9. Nếu Vault server nằm ngoài Kubernetes cluster, bước cấu hình reviewer/CA nào không còn được lấy tự động từ local Pod?
10. Bạn cần kiểm thử nào để chứng minh workload không thể đọc KV của ứng dụng khác dù dùng cùng auth mount?

### Tài liệu tham khảo

- [HashiCorp Vault — Kubernetes auth method](https://developer.hashicorp.com/vault/docs/auth/kubernetes)
- [HashiCorp Vault — Kubernetes auth HTTP API, config/role/login](https://developer.hashicorp.com/vault/api-docs/auth/kubernetes)
- [HashiCorp Vault — Manage Vault access with Kubernetes ServiceAccounts](https://developer.hashicorp.com/validated-patterns/vault/vault-kubernetes-auth)
- [HashiCorp Vault — Auto-auth with Kubernetes (Vault Agent)](https://developer.hashicorp.com/vault/docs/agent-and-proxy/autoauth/methods/kubernetes)
- [Kubernetes — ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/)
- [Kubernetes — Configure ServiceAccounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- [Spring Vault — Authentication methods: Kubernetes](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — KubernetesAuthentication API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/KubernetesAuthentication.html)
- [Spring Vault — KubernetesAuthenticationOptions API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/KubernetesAuthenticationOptions.html)
- [Spring Vault — VaultKeyValueOperations API](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/core/VaultKeyValueOperations.html)
- [HashiCorp Vault — Token và lease lifecycle](https://developer.hashicorp.com/vault/docs/concepts/tokens)
