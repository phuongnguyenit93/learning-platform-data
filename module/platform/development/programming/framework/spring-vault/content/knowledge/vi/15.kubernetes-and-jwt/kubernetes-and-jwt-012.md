# Kiểm thử quyền của workload theo namespace và role

## 1. Mục tiêu và mô hình phân quyền

Khi triển khai ứng dụng Java trong Kubernetes, **Spring Vault** cho phép workload lấy secret từ HashiCorp Vault thông qua `VaultTemplate` mà không cần lưu một Vault token dài hạn trong image, biến môi trường hay Git. Workload có thể trình **ServiceAccount token dạng JWT** để đăng nhập vào Vault, nhận một Vault token ngắn hạn rồi dùng token đó gọi các API được cho phép.

Trong chương **Kubernetes và JWT**, vấn đề quan trọng không chỉ là đăng nhập thành công, mà là **chứng minh mỗi workload chỉ được nhận đúng quyền trong namespace và role của nó**. Một pod trong `team-dev` không được giả danh pod ở `team-prod`; workload `payments` không được dùng quyền `orders`; kể cả workload `orders` đăng nhập hợp lệ cũng không được đọc secret ngoài phạm vi được cấp.

Sau bài học, bạn có thể:

- Phân biệt namespace/ServiceAccount của Kubernetes, **role của phương thức xác thực Vault** và **Vault ACL policy**.
- Cấu hình một kịch bản lab có role ràng buộc theo tên ServiceAccount, namespace và JWT audience.
- Kiểm thử cả đăng nhập hợp lệ, đăng nhập bị từ chối và đăng nhập hợp lệ nhưng đọc secret bị từ chối.
- Giải thích sự khác biệt khi dùng **Kubernetes auth** (TokenReview) và **JWT auth** (kiểm tra chữ ký/claims).
- Đưa phép thử này vào kiểm thử tích hợp cho workload sử dụng `VaultTemplate`, đồng thời xử lý token hết hạn, lỗi quyền và quan sát audit.

### Ba lớp quyền phải được kiểm tra riêng

| Lớp | Ai kiểm tra? | Câu hỏi cần trả lời |
| --- | --- | --- |
| Kubernetes ServiceAccount / RBAC | Kubernetes API Server và admission | Pod có thể chạy dưới ServiceAccount nào? Chủ thể đó được gọi những API Kubernetes nào? |
| Vault auth role | Backend `auth/kubernetes` hoặc `auth/jwt` | JWT có thuộc workload, namespace, subject và audience mà role cho phép không? |
| Vault ACL policy | Vault khi ứng dụng gọi secret API | Vault token nhận được có quyền `read`, `list`, `update`... trên đường dẫn cụ thể hay không? |

**Vault role không phải Kubernetes `Role` hay `RoleBinding`.** Hai hệ thống sử dụng thuật ngữ “role”, nhưng chúng bảo vệ những tài nguyên khác nhau. Kubernetes RBAC không tự cấp quyền Vault; đăng nhập Vault thành công cũng không tự cấp quyền đọc mọi secret.

## 2. Kịch bản lab và ma trận kỳ vọng

Giả sử có một cụm Kubernetes với ba workload:

| Workload | Namespace | ServiceAccount | Vai trò kiểm thử |
| --- | --- | --- | --- |
| Orders Dev | `team-dev` | `orders` | Được vào Vault role `orders-dev`, chỉ đọc secret Dev của Orders. |
| Payments Dev | `team-dev` | `payments` | Không được vào role `orders-dev`. |
| Orders Prod | `team-prod` | `orders` | Được vào role `orders-prod`, không được dùng role Dev. |

Giả định Vault đã có mount KV v2 tại `secret/`, với hai key thử nghiệm:

- `secret/data/team-dev/orders/config`
- `secret/data/team-prod/orders/config`

Đường dẫn `secret/data/...` là **API path** dành cho KV v2 khi viết Vault policy. Trong CLI `vault kv get -mount=secret team-dev/orders/config`, phần `data/` do lệnh KV v2 xử lý. Không thêm `data/` hai lần.

Quy tắc mong đợi:

~~~mermaid
flowchart LR
    D["Pod team-dev / SA orders"] -->|"JWT audience=vault"| A["Vault Kubernetes auth"]
    P["Pod team-dev / SA payments"] -->|"JWT audience=vault"| A
    R["Pod team-prod / SA orders"] -->|"JWT audience=vault"| A
    A -->|"Role kiểm tra namespace + SA + audience"| T["Vault token có ACL"]
    T -->|"read đường dẫn được cấp"| S["KV v2 secret/data/..."]
    A -->|"Không khớp role"| X["Đăng nhập bị từ chối"]
    T -->|"Đường dẫn ngoài policy"| Y["403 permission denied"]
~~~

Trong lab, dấu “thành công” phải gồm **hai điều kiện**: xác thực đúng workload *và* truy cập đúng secret; một response đăng nhập thành công đơn lẻ không chứng minh cách ly dữ liệu.

## 3. JWT workload được tạo và kiểm tra như thế nào?

Một Kubernetes ServiceAccount token hiện đại thường được cấp qua **TokenRequest API** và có thời hạn. Token là JWT chứa các thông tin như issuer (`iss`), audience (`aud`), thời hạn (`exp`), subject (`sub`) và các claim gắn với ServiceAccount/Pod.

Ví dụ subject:

~~~text
sub = system:serviceaccount:team-dev:orders
~~~

Giá trị trên gắn danh tính `orders` với namespace `team-dev`. Cùng tên ServiceAccount `orders` trong `team-prod` sẽ có subject **khác**:

~~~text
sub = system:serviceaccount:team-prod:orders
~~~

Khi một workload đăng nhập bằng **Kubernetes auth**:

1. Workload cung cấp JWT của ServiceAccount cùng tên role Vault muốn đăng nhập.
2. Vault gọi Kubernetes **TokenReview API** thông qua thông tin cấu hình auth method và reviewer credential hợp lệ.
3. Kubernetes kiểm tra token, trả về danh tính ServiceAccount cùng thông tin xác thực; Vault đối chiếu với ràng buộc của role như `bound_service_account_names`, `bound_service_account_namespaces` và `audience`.
4. Nếu hợp lệ, Vault phát hành **Vault token** kèm các policy đã cấu hình cho role.
5. Mọi lệnh đọc secret tiếp theo dùng Vault token và tiếp tục phải vượt qua kiểm tra Vault ACL.

Không tin vào tên namespace do client tự gửi trong body đăng nhập. Namespace và ServiceAccount phải được suy ra từ **JWT đã được xác thực**, chứ không từ tham số không đáng tin cậy.

**Audience là một biên giới tin cậy.** Token tạo để gọi Kubernetes API có thể có audience khác với token dành riêng cho Vault. Đặt role Vault yêu cầu `audience=vault` và cấp JWT cho đúng audience; cùng lúc phải bảo đảm TokenReview và cấu hình Vault phù hợp với phiên bản Kubernetes/Vault đang sử dụng.

## 4. Chuẩn bị danh tính Kubernetes cho ba trường hợp

Trên cụm lab, tạo hai namespace và các ServiceAccount tương ứng. Ví dụ manifest:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: team-dev
---
apiVersion: v1
kind: Namespace
metadata:
  name: team-prod
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders
  namespace: team-dev
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: payments
  namespace: team-dev
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders
  namespace: team-prod
~~~

Áp dụng manifest ở một môi trường thử nghiệm do nhóm quản trị cụm cho phép, rồi kiểm tra:

~~~bash
kubectl -n team-dev get sa orders payments
kubectl -n team-prod get sa orders
~~~

Để một Vault server sử dụng Kubernetes auth có thể gọi TokenReview, cần cấu hình reviewer với quyền Kubernetes phù hợp. Một phương án là gán ClusterRole `system:auth-delegator` cho ServiceAccount reviewer chuyên dụng:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: vault-reviewer-tokenreview
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:auth-delegator
subjects:
  - kind: ServiceAccount
    name: vault-reviewer
    namespace: vault-system
~~~

Ví dụ binding này giả định đã tạo ServiceAccount `vault-reviewer` trong namespace `vault-system`. Với Vault chạy **trong Kubernetes**, có thể dùng token của chính Pod Vault nếu ServiceAccount đó có quyền TokenReview; với Vault chạy ngoài cụm phải quản trị reviewer credential và vòng đời token một cách phù hợp. Không dùng token workload Orders để thay thế reviewer credential nếu không có thiết kế và quyền tương ứng.

Kiểm tra quyền reviewer, không nhầm với quyền đọc secret Vault:

~~~bash
kubectl auth can-i create tokenreviews \
  --as=system:serviceaccount:vault-system:vault-reviewer
~~~

Kết quả mong đợi là `yes` khi reviewer đã có quyền phù hợp. Lệnh kiểm tra `--as` phụ thuộc quyền impersonate của người chạy; người không có quyền đó sẽ nhận lỗi Kubernetes RBAC.

## 5. Cấu hình Vault auth role và policy tách theo namespace

Các lệnh cấu hình sau chạy bằng **danh tính quản trị Vault trong lab**, không dùng token của ứng dụng.

### 5.1. Policy chỉ đọc đúng secret Dev/Prod

Policy cho Orders Dev:

~~~hcl
# orders-dev-read.hcl
path "secret/data/team-dev/orders/config" {
  capabilities = ["read"]
}
~~~

Policy cho Orders Prod:

~~~hcl
# orders-prod-read.hcl
path "secret/data/team-prod/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp hai policy sau khi lưu nội dung HCL tương ứng:

~~~bash
vault policy write orders-dev-read orders-dev-read.hcl
vault policy write orders-prod-read orders-prod-read.hcl
~~~

Mỗi policy chỉ cấp `read` trên **một** đường dẫn. Không dùng `secret/*` hoặc `secret/data/*` cho workload chỉ cần đọc cấu hình của chính nó.

Có thể tạo hai key dữ liệu giả trước khi kiểm thử:

~~~bash
vault kv put -mount=secret team-dev/orders/config username=orders-dev-lab
vault kv put -mount=secret team-prod/orders/config username=orders-prod-lab
~~~

Tất cả giá trị trên là dữ liệu lab. Không đưa secret production hoặc Vault root token vào ví dụ, file test hay log CI.

### 5.2. Kích hoạt và cấu hình Kubernetes auth

Nếu chưa có auth method ở đường dẫn `kubernetes/`:

~~~bash
vault auth enable -path=kubernetes kubernetes
~~~

Vault Kubernetes auth phải được cấu hình kết nối đến API server, CA phù hợp và reviewer credential (hoặc cấu hình dùng token/CA trong Pod Vault). Ví dụ khi thông tin đã được cấp an toàn cho quá trình cấu hình:

~~~bash
vault write auth/kubernetes/config \
  kubernetes_host="$K8S_API_URL" \
  kubernetes_ca_cert=@"$K8S_CA_CERT_FILE" \
  token_reviewer_jwt="$REVIEWER_JWT"
~~~

`K8S_API_URL`, `K8S_CA_CERT_FILE` và `REVIEWER_JWT` là các giá trị môi trường được chuẩn bị riêng, **không phải** literal có thể copy để chạy ngay. Reviewer JWT có thể hết hạn, vì vậy cấu hình production phải có chiến lược cấp/đổi credential hoặc sử dụng cơ chế local service account token phù hợp với môi trường triển khai. Nếu mount auth đã tồn tại, kiểm tra cấu hình hiện tại trước khi thay đổi.

### 5.3. Ràng buộc role bằng ServiceAccount, namespace và audience

~~~bash
vault write auth/kubernetes/role/orders-dev \
  bound_service_account_names=orders \
  bound_service_account_namespaces=team-dev \
  audience=vault \
  token_policies=orders-dev-read \
  token_ttl=15m

vault write auth/kubernetes/role/orders-prod \
  bound_service_account_names=orders \
  bound_service_account_namespaces=team-prod \
  audience=vault \
  token_policies=orders-prod-read \
  token_ttl=15m

vault read auth/kubernetes/role/orders-dev
vault read auth/kubernetes/role/orders-prod
~~~

Role `orders-dev` chấp nhận đúng ServiceAccount `orders` thuộc `team-dev`; role `orders-prod` chấp nhận `orders` thuộc `team-prod`. Tên role trong yêu cầu đăng nhập là do client chọn, nên **chỉ riêng tên role không thể tạo ra quyền**: Vault vẫn phải kiểm tra JWT và các ràng buộc của role đó.

Ba trường cần đọc lại sau khi cấu hình là `bound_service_account_names`, `bound_service_account_namespaces` và `token_policies`. Cần tránh cấu hình wildcard như `bound_service_account_namespaces="*"` khi chưa có yêu cầu cụ thể và phép thử chứng minh quyền thực sự được giới hạn ở nơi khác.

**Phân biệt:** Kubernetes namespace `team-dev` và Vault Enterprise namespace (nếu được bật) là hai khái niệm độc lập. Bài này chỉ kiểm thử namespace của **Kubernetes ServiceAccount**; mọi lệnh Vault giả định chạy trong cùng một ngữ cảnh Vault namespace đã xác định.

## 6. Chạy đăng nhập tích cực và tiêu cực

Trong lab Kubernetes hỗ trợ TokenRequest, `kubectl create token` giúp tạo JWT ngắn hạn tương ứng với từng ServiceAccount. Lệnh này đòi hỏi người chạy có quyền Kubernetes `create` trên tài nguyên `serviceaccounts/token`; đây là **công cụ kiểm thử của người quản trị**, không phải quyền nên cấp đại trà cho workload.

Tạo ba token có audience `vault`:

~~~bash
set +x  # Không bật shell trace khi thao tác với JWT/token.

DEV_ORDERS_JWT="$(kubectl -n team-dev create token orders --audience=vault --duration=10m)"
DEV_PAYMENTS_JWT="$(kubectl -n team-dev create token payments --audience=vault --duration=10m)"
PROD_ORDERS_JWT="$(kubectl -n team-prod create token orders --audience=vault --duration=10m)"
~~~

Đăng nhập đúng role Dev, lấy Vault token từ JSON trả về. Ví dụ này dùng công cụ `jq`:

~~~bash
DEV_RESPONSE="$(vault write -format=json auth/kubernetes/login \
  role=orders-dev jwt="$DEV_ORDERS_JWT")"

DEV_VAULT_TOKEN="$(printf '%s' "$DEV_RESPONSE" | jq -er '.auth.client_token')"
~~~

Giữ JWT và Vault token trong shell tạm, không `echo` nguyên token, không ghi vào artifacts CI. Sau khi đăng nhập thành công, kiểm tra **Vault ACL thực tế**:

~~~bash
# Được phép: đọc đúng key Dev.
VAULT_TOKEN="$DEV_VAULT_TOKEN" \
  vault kv get -mount=secret team-dev/orders/config

# Phải bị từ chối: role Dev không có quyền key Prod.
VAULT_TOKEN="$DEV_VAULT_TOKEN" \
  vault kv get -mount=secret team-prod/orders/config
~~~

Lệnh thứ hai phải thất bại do không có capability `read` phù hợp. Không được coi mọi lỗi là bằng chứng ACL đúng: cần phân biệt `403 permission denied` với lỗi mạng, Vault unavailable, thiếu key hoặc cấu hình mount sai.

### Ma trận kiểm thử bắt buộc

| JWT được cấp cho | Role đăng nhập | Kỳ vọng đăng nhập | Kỳ vọng truy cập secret |
| --- | --- | --- | --- |
| `team-dev / orders` | `orders-dev` | **PASS** | Đọc `team-dev/orders/config` PASS. |
| `team-dev / payments` | `orders-dev` | **DENY** | Không được cấp Vault token cho role này. |
| `team-prod / orders` | `orders-dev` | **DENY** | Không được cấp Vault token cho role Dev. |
| `team-dev / orders` | `orders-prod` | **DENY** | Không được cấp Vault token cho role Prod. |
| `team-prod / orders` | `orders-prod` | **PASS** | Đọc `team-prod/orders/config` PASS. |
| `team-dev / orders` | `orders-dev` | **PASS** | Đọc `team-prod/orders/config` **DENY** bởi ACL. |
| JWT sai audience hoặc đã hết hạn | Role tương ứng | **DENY** | Không có phiên đăng nhập hợp lệ để đọc secret. |

Ma trận kiểm tra **ràng buộc danh tính** trước và **phân quyền tài nguyên** sau đăng nhập. Nếu chỉ kiểm tra trường hợp đúng, một cấu hình role chấp nhận namespace quá rộng có thể lọt qua mà không được phát hiện.

### Kịch bản Bash có assertion

Đoạn sau dùng Vault CLI và `jq` trong một môi trường test đã cấu hình sẵn. Nó không in token ra màn hình; khi login thất bại, chỉ ghi PASS/FAIL cho từng ca.

~~~bash
#!/usr/bin/env bash
set -euo pipefail
set +x

login() {
  local ns="$1" sa="$2" role="$3"
  local jwt
  jwt="$(kubectl -n "$ns" create token "$sa" --audience=vault --duration=10m)"
  vault write -format=json auth/kubernetes/login role="$role" jwt="$jwt"
}

expect_login_denied() {
  local ns="$1" sa="$2" role="$3"
  if login "$ns" "$sa" "$role" >/dev/null 2>&1; then
    echo "FAIL: $ns/$sa được vào role $role"
    return 1
  fi
  echo "PASS: $ns/$sa bị từ chối role $role"
}

# Đăng nhập đúng và bắt buộc nhận token hợp lệ.
dev_login="$(login team-dev orders orders-dev)"
dev_token="$(printf '%s' "$dev_login" | jq -er '.auth.client_token')"
echo "PASS: team-dev/orders đăng nhập orders-dev"

expect_login_denied team-dev payments orders-dev
expect_login_denied team-prod orders orders-dev
expect_login_denied team-dev orders orders-prod

prod_login="$(login team-prod orders orders-prod)"
prod_token="$(printf '%s' "$prod_login" | jq -er '.auth.client_token')"
echo "PASS: team-prod/orders đăng nhập orders-prod"

if VAULT_TOKEN="$dev_token" vault kv get -mount=secret \
    team-dev/orders/config >/dev/null 2>&1; then
  echo "PASS: Dev đọc secret Dev"
else
  echo "FAIL: Dev không đọc được secret Dev"
  exit 1
fi

if VAULT_TOKEN="$dev_token" vault kv get -mount=secret \
    team-prod/orders/config >/dev/null 2>&1; then
  echo "FAIL: Dev đọc được secret Prod"
  exit 1
else
  echo "PASS: Dev bị từ chối secret Prod (xem audit để xác nhận 403)"
fi

if VAULT_TOKEN="$prod_token" vault kv get -mount=secret \
    team-prod/orders/config >/dev/null 2>&1; then
  echo "PASS: Prod đọc secret Prod"
else
  echo "FAIL: Prod không đọc được secret Prod"
  exit 1
fi
~~~

Script kiểm tra exit status và ranh giới quyền; với ca truy cập bị từ chối, **cần xem phản hồi HTTP hoặc Vault audit log** để chắc chắn đó là `403` do ACL, thay vì gộp lỗi kết nối/DNS thành một lần kiểm thử bảo mật thành công.

## 7. Đưa JWT đúng audience vào Pod thực tế

Trong Pod, kubelet có thể cung cấp token ngắn hạn dưới dạng **projected ServiceAccount token**. Đây là cách phù hợp để workload định danh, thay vì sao chép token thử nghiệm tạo bởi `kubectl create token` vào Secret Kubernetes hay container image.

Ví dụ Pod chỉ minh họa cấu hình danh tính:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders-vault-check
  namespace: team-dev
spec:
  serviceAccountName: orders
  automountServiceAccountToken: false
  containers:
    - name: client
      image: curlimages/curl:8.10.1
      command: ["sh", "-c", "sleep 3600"]
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
              expirationSeconds: 600
~~~

Pod có token tại `/var/run/secrets/vault/token` dành riêng cho audience `vault`. Kubelet chịu trách nhiệm cấp và xoay projected token theo cơ chế Kubernetes. Khi triển khai ứng dụng Java, cấu hình cơ chế **Kubernetes authentication** của Spring Vault đọc token từ đường dẫn này, đăng nhập bằng role `orders-dev`, và sử dụng session Vault thu được để `VaultTemplate` truy cập KV v2.

Không giả định ServiceAccount token mặc định ở `/var/run/secrets/kubernetes.io/serviceaccount/token` luôn có audience phù hợp với Vault. Trong manifest trên, `automountServiceAccountToken: false` tắt mount token mặc định, còn projected volume được khai báo tường minh vẫn cung cấp token cho Vault.

### Tách cấu hình xác thực khỏi code đọc secret

Khi `VaultTemplate` đã được cấu hình sử dụng một `SessionManager` xác thực bằng Kubernetes auth, business service chỉ cần đọc key:

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.Versioned;

@Service
public class OrdersConfigurationReader {

    private final VaultTemplate vaultTemplate;

    public OrdersConfigurationReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public String readUsername() {
        Versioned<Map<String, Object>> secret =
            vaultTemplate.opsForVersionedKeyValue("secret")
                         .get("team-dev/orders/config");

        if (secret == null || secret.getData() == null) {
            throw new IllegalStateException("Orders configuration unavailable");
        }

        Object username = secret.getData().get("username");
        if (!(username instanceof String)) {
            throw new IllegalStateException("Invalid Orders configuration");
        }
        return (String) username;
    }
}
~~~

Đường dẫn tương đối `team-dev/orders/config` được xử lý bởi các **versioned KV operations** của Spring Vault; không viết `secret/data/...` vào lời gọi `get` khi đã truyền mount `secret`.

Kiểm thử Spring service này theo hai lớp: unit test kiểm tra hành vi khi key thiếu hoặc dữ liệu sai kiểu; integration test chạy bằng danh tính Kubernetes thực để xác nhận lỗi `403` từ Vault khi role đúng nhưng đường dẫn ngoài policy. Mock `VaultTemplate` không thể chứng minh ràng buộc namespace của Kubernetes TokenReview.

## 8. Cùng workload JWT nhưng dùng Vault JWT auth thì khác gì?

Vault hỗ trợ cả **Kubernetes auth** và **JWT auth**. Cả hai có thể dùng JWT của Kubernetes ServiceAccount, nhưng **khác cách xác minh**:

| Tiêu chí | Kubernetes auth | JWT auth |
| --- | --- | --- |
| Endpoint login | `auth/kubernetes/login` | `auth/jwt/login` nếu mount JWT ở `jwt/`. |
| Kiểm tra danh tính | Kubernetes TokenReview và ràng buộc Vault role. | Xác minh chữ ký JWT bằng issuer/JWKS/OIDC discovery hoặc public key được cấu hình, rồi kiểm tra claims. |
| Namespace/SA | `bound_service_account_names`, `bound_service_account_namespaces`. | Ràng buộc subject/claims, ví dụ `bound_subject` hoặc `bound_claims`. |
| Audience | `audience` trong role Kubernetes auth. | `bound_audiences` trong role JWT auth. |
| Khi ServiceAccount/Pod bị thay đổi | TokenReview có khả năng phản ánh trạng thái token được Kubernetes công nhận khi đăng nhập. | JWT auth chủ yếu dựa trên chữ ký, issuer, audience, thời gian và claims; việc thu hồi tức thời một JWT đã phát hành không tự được đảm bảo chỉ bằng kiểm tra chữ ký. |

Chẳng hạn, sau khi đã cấu hình một JWT auth mount tin cậy đúng issuer/key của Kubernetes và các thuộc tính xác minh bắt buộc, một role JWT có thể ràng buộc subject đầy đủ:

~~~bash
# Chỉ thực hiện khi auth/jwt đã được cấu hình xác minh issuer/chữ ký.
vault write auth/jwt/role/orders-dev \
  role_type=jwt \
  user_claim=sub \
  bound_subject="system:serviceaccount:team-dev:orders" \
  bound_audiences=vault \
  token_policies=orders-dev-read
~~~

Khi dùng JWT auth, workload đăng nhập tại `auth/jwt/login` với cùng dạng `role` và `jwt` nhưng JWT plugin **không gọi Kubernetes TokenReview theo cách của Kubernetes auth**. Vì vậy, phải kiểm tra cấu hình xác thực chữ ký, issuer, audience, subject và thời hạn trước khi tin cậy claims. Không so sánh hai auth method bằng tên role: một tên role giống nhau tại hai mount là **hai cấu hình độc lập**.

Với cả hai phương thức, Vault token phát hành sau login chỉ có quyền theo **Vault ACL policy** tương ứng. Ma trận test ở phần 6 vẫn cần chạy, nhưng phép thử phải dùng endpoint login và tiêu chí xác minh thích hợp với từng auth method.

## 9. Lỗi quyền, lỗi xác thực và dấu vết giám sát

Không phải mọi lần thất bại đều do namespace hoặc role. Phân biệt nguyên nhân giúp tránh sửa policy sai chỗ:

| Hiện tượng | Nguyên nhân có thể | Kiểm tra tiếp |
| --- | --- | --- |
| `auth/kubernetes/login` thất bại ngay cả với SA đúng | Reviewer không gọi được TokenReview, CA/URL API sai, JWT hết hạn hoặc audience không khớp. | Vault auth config, quyền `tokenreviews`, issuer/audience, thời hạn token và kết nối API. |
| `team-dev/payments` đăng nhập `orders-dev` được | Role có thể ràng buộc tên SA quá rộng hoặc cấu hình khác dự kiến. | Đọc lại `bound_service_account_names`, namespace, audience, policy và đúng auth mount. |
| `team-prod/orders` vào role Dev được | Role đang cho phép namespace quá rộng hoặc nhầm auth role. | Kiểm tra `bound_service_account_namespaces` và đường dẫn mount được gọi. |
| Login PASS nhưng `vault kv get` trả `403` | Vault token không có `read` trên API path KV v2. | So khớp `secret/data/...`, `token_policies` và capability thực tế. |
| Login PASS nhưng KV trả `404` | Key/path không tồn tại, phiên bản secret đã bị xóa hoặc người dùng đang gọi sai mount. | Kiểm tra KV v2 path và trạng thái dữ liệu bằng danh tính được phép. |
| Một phần test fail sau một khoảng thời gian | Kubernetes JWT hoặc Vault token hết hạn, clock skew, audience sai. | Kiểm tra `exp`, thời gian máy, cách rotation và chính sách TTL. |
| Workload cũ vẫn đọc được sau khi đổi ràng buộc role | Token Vault đã phát hành có thể còn hiệu lực theo TTL của nó. | Xem xét revoke token đã cấp, thời hạn token và các thay đổi policy tương ứng. |

Khi có quyền và môi trường phù hợp, đọc capability thực tế từ **Vault token của workload**:

~~~bash
VAULT_TOKEN="$DEV_VAULT_TOKEN" vault token capabilities \
  secret/data/team-dev/orders/config

VAULT_TOKEN="$DEV_VAULT_TOKEN" vault token capabilities \
  secret/data/team-prod/orders/config
~~~

Kết quả kỳ vọng là có `read` đối với key Dev và `deny` đối với key Prod, trong điều kiện các policy thực tế giống thiết kế lab. Kiểm tra capability bổ trợ cho bài test đọc thật nhưng không thay thế request truy cập dữ liệu.

Trong môi trường tích hợp, bật **Vault audit device** bằng cơ chế quản trị phù hợp để quan sát auth mount, role, entity, policy và request path. Đối chiếu request ID/trace của login với request đọc secret sau đó, phân biệt `403` tại **login** với `403` tại **KV API**. Không log JWT, Vault token, reviewer JWT hay giá trị secret; audit log cũng phải được bảo vệ như dữ liệu bảo mật.

Theo dõi tỷ lệ login bị từ chối theo role/namespace, lỗi TokenReview, `403` trên KV, token hết hạn và độ trễ auth. Mẫu lỗi tăng mạnh sau khi đổi reviewer credential hoặc audience có thể là lỗi cấu hình chung, không có nghĩa tất cả workload cùng vi phạm ACL.

## 10. Các trường hợp lạm dụng cần mô phỏng

Ngoài happy path, bài kiểm thử phân quyền cần làm rõ các giả định về ranh giới tin cậy:

1. **Trùng tên ServiceAccount giữa các namespace:** tạo `orders` ở cả Dev và Prod, rồi xác nhận Dev role không chấp nhận JWT Prod. Đây là phép thử phát hiện thiếu điều kiện namespace.
2. **Khác ServiceAccount nhưng cùng namespace:** `payments` tại `team-dev` không được giả làm `orders` bằng cách chọn role `orders-dev`.
3. **Role đúng, secret sai:** JWT hợp lệ cho Dev nhưng KV path Prod vẫn phải bị từ chối bởi ACL.
4. **Audience không đúng:** tạo JWT cho audience khác (chẳng hạn `kubernetes.default.svc` nếu phù hợp cấu hình cụm) rồi thử role yêu cầu `vault`; phải từ chối.
5. **Token hết hạn:** dùng TTL thử nghiệm ngắn, chờ đến khi JWT hết hạn hoặc dùng một JWT đã hết hạn; login mới phải thất bại. Kiểm thử này có thời gian chờ, nên có thể đặt trong bộ integration test chuyên biệt.
6. **Thay đổi role sau khi phát hành Vault token:** sửa điều kiện role trong lab, thử login lại và kiểm tra cách xử lý các Vault token đã cấp. **Thay đổi điều kiện đăng nhập không tự bảo đảm thu hồi mọi Vault token cũ**; thiết kế TTL và revoke token phù hợp.
7. **Người có quyền tạo Pod trong namespace:** nếu một principal có thể tạo Pod chạy dưới ServiceAccount `orders` trong `team-dev`, principal đó có thể có cách lấy danh tính workload tương ứng tùy admission và quyền thực tế. Bảo vệ việc tạo Pod, dùng ServiceAccount và TokenRequest cũng là một phần của kiểm soát truy cập.

Ở ca số 7, chỉ nhìn vào Vault role không đủ để kết luận một tenant không thể lấy JWT của workload khác. Cần bổ sung kiểm tra Kubernetes RBAC, admission policy, quyền tạo Pod, quyền `serviceaccounts/token` và cấu hình automount/projected token. Việc dùng namespace làm ranh giới cần dựa trên bảo vệ thực tế của Kubernetes cluster.

### Chiến lược kiểm thử tích hợp

Để xác nhận end-to-end, sử dụng một cụm Kubernetes dành cho integration test (ví dụ cụm tạm), một Vault test được kết nối đến Kubernetes API, reviewer có quyền TokenReview, hai namespace và các ServiceAccount như trên. Kiểm thử thao tác thật: **cấp JWT → login Vault → nhận Vault token → gọi KV v2 → xác nhận kết quả**.

Testcontainers chỉ chạy riêng Vault là chưa đủ để kiểm tra ràng buộc danh tính Kubernetes nếu không có TokenReview API thật. Dùng mock phù hợp cho unit test của Java service, nhưng phép thử namespace/role phải có một bộ tích hợp xác minh được danh tính workload.

### Checklist trước khi kết luận PASS

- [ ] Vault Kubernetes auth có reviewer hợp lệ, kết nối CA/API tin cậy và kiểm tra audience theo thiết kế.
- [ ] Role giới hạn chính xác ServiceAccount, namespace và policy; không có wildcard ngoài yêu cầu.
- [ ] Role Dev và Prod cấp policy khác nhau theo **API path KV v2**.
- [ ] Có cả ca login PASS, login DENY và login PASS nhưng KV read DENY.
- [ ] Lỗi từ chối KV được xác nhận là lỗi quyền, không phải lỗi mạng hoặc key thiếu.
- [ ] Kết quả ghi nhận role, namespace, ServiceAccount, loại lỗi và request ID cần thiết, nhưng không lộ token/secret.
- [ ] Thời hạn JWT, Vault token, rotation và revoke được kiểm tra theo vòng đời workload.
- [ ] Quyền Kubernetes tạo Pod và ServiceAccount token được kiểm tra cùng Vault role.

## 11. Câu hỏi tự đánh giá

1. Vì sao chỉ đặt `token_policies=orders-dev-read` cho role mà không giới hạn ServiceAccount và namespace vẫn là một cấu hình nguy hiểm?
2. Tại sao đăng nhập thành công `orders-dev` **không** chứng minh workload có quyền đọc `secret/data/team-prod/orders/config`?
3. Có hai ServiceAccount cùng tên `orders` ở hai namespace khác nhau. Vault role phải ràng buộc thêm thuộc tính gì để tách biệt chúng?
4. Khi một request login thất bại, làm thế nào phân biệt reviewer không có quyền TokenReview với JWT có audience sai?
5. Kubernetes auth và JWT auth khác nhau ra sao trong việc xác nhận ServiceAccount token? Tại sao JWT auth cần kiểm tra chữ ký và issuer độc lập với các bound claims?
6. Tại sao đổi ràng buộc auth role chưa chắc làm Vault token đã cấp trước đó mất hiệu lực ngay? Cần thiết kế TTL/revoke như thế nào?
7. Vì sao kiểm thử `kubectl auth can-i` về Kubernetes RBAC và kiểm thử `vault token capabilities` về Vault ACL đều cần thiết nhưng không thay thế nhau?

## Tài liệu tham khảo chính thức

- [HashiCorp Vault — Kubernetes auth method](https://developer.hashicorp.com/vault/docs/auth/kubernetes).
- [HashiCorp Vault — JWT/OIDC auth method](https://developer.hashicorp.com/vault/docs/auth/jwt).
- [HashiCorp Vault — KV secrets engine v2](https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2).
- [Kubernetes — Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).
- [Kubernetes — Projected volumes và ServiceAccount token](https://kubernetes.io/docs/concepts/storage/projected-volumes/).

Điểm cốt lõi khi kiểm thử quyền workload là xác nhận **danh tính đã được Kubernetes xác thực, role Vault ràng buộc đúng namespace/ServiceAccount và Vault policy chỉ cho phép truy cập secret cần thiết**. Ba lớp cần được kiểm tra bằng cả ca thành công lẫn ca bị từ chối.
