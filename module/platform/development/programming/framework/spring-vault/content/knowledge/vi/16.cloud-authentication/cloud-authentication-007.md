# GCP GCE và chứng minh danh tính từ metadata trong Spring Vault

Một ứng dụng Java chạy trên **Google Compute Engine (GCE)** cần đọc KV secrets, dùng Transit encryption hoặc phát hành chứng chỉ PKI từ **HashiCorp Vault** thông qua **Spring Vault** (ví dụ `VaultTemplate`). Thay vì nhúng sẵn Vault token hay khóa JSON của service account vào ứng dụng, ta có thể sử dụng phương thức **Vault GCP authentication kiểu GCE**: ứng dụng nhận **identity JWT được Google ký** từ metadata server của VM, gửi JWT đó tới Vault để chứng minh danh tính, và nhận về **Vault client token** có policy/TTL do Vault cấp.

Bài này thuộc chương **Xác thực cloud** và giải thích cơ chế GCE identity, các ràng buộc xác thực, ví dụ cấu hình và lệnh chạy thử, cách tích hợp Spring Cloud Vault/Spring Vault, xử lý lỗi, giám sát và kiểm thử tích hợp. Trọng tâm là **danh tính GCE từ metadata**; Vault IAM auth, Kubernetes auth và Google OAuth access token là các cơ chế khác cần phân biệt.

## 1. Danh tính nào được dùng để đăng nhập?

| Loại credential | Nguồn phát hành | Tác dụng | Điểm cần nhớ |
| --- | --- | --- | --- |
| **GCE instance identity JWT** | Google, qua GCE metadata server | Chứng minh instance/workload GCE với Vault GCP GCE auth. | Có chữ ký Google, `aud`, `exp` và thông tin nhận diện instance. |
| **Google OAuth access token** | Google | Cho phép gọi Google Cloud APIs theo quyền của service account. | Không thay thế được identity JWT mà GCE auth yêu cầu. |
| **Vault client token** | Vault sau khi đăng nhập thành công | Gọi API KV, Transit, PKI... theo Vault policy. | Có TTL và cơ chế renew/revoke riêng; không phải token Google. |

Các khái niệm này tạo ba lớp tách biệt:

1. **Google chứng minh VM là ai** qua một identity JWT cấp tại metadata server.
2. **Vault quyết định VM ấy có thuộc role được chấp nhận không**, dựa vào chữ ký, audience, thời hạn, project/zone và các ràng buộc khác.
3. **Vault policy quyết định quyền nghiệp vụ** trên các secret engines, sau khi Vault token đã được phát hành.

Một JWT có chữ ký hợp lệ không đồng nghĩa VM có thể đăng nhập mọi Vault role. Đăng nhập thành công cũng không đồng nghĩa có thể đọc mọi secret.

## 2. Luồng xác thực từ GCE metadata đến VaultTemplate

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Java / Spring Vault trên GCE
    participant Meta as GCE Metadata Server
    participant Auth as Vault GCP Auth
    participant Engine as KV / Transit / PKI
    App->>Meta: GET .../identity?audience=vault/orders-gce&format=full
    Note over App,Meta: Metadata-Flavor: Google
    Meta-->>App: Google-signed identity JWT
    App->>Auth: POST /v1/auth/gcp/login (role, jwt)
    Auth->>Auth: Verify signature, exp, aud, GCE claims và role
    Auth-->>App: Vault token, policies, TTL, renewable
    App->>Engine: Gọi API với Vault token
    Engine-->>App: Secret / kết quả / permission denied
~~~

**Các bước chi tiết:**

1. Ứng dụng trên GCE gọi metadata endpoint của instance với header `Metadata-Flavor: Google`.
2. Google trả identity JWT được ký với `audience` xác định, thường là `vault/<tên-role>` đối với GCE auth.
3. Spring Vault gửi `role` và `jwt` qua HTTPS tới `/v1/auth/gcp/login` hoặc auth mount được cấu hình riêng.
4. Vault xác minh tính hợp lệ của JWT và các ràng buộc role như project/zone, sau đó phát hành Vault token.
5. Client dùng Vault token để gọi API trên secret engine. Khi token hết hạn, client quản lý phiên phù hợp có thể renew hoặc xác thực lại với một JWT mới.

**Ranh giới bảo mật:** metadata server chỉ phục vụ trong môi trường GCE phù hợp; HTTP tới metadata là đường truy cập nội bộ do nền tảng cung cấp. Đường từ ứng dụng đến Vault phải dùng HTTPS và xác minh chứng chỉ TLS. Không in identity JWT hoặc Vault token ra log, console, trace hay hệ thống giám sát.

### Audience và chứng minh đúng đối tượng

Với Vault role `orders-gce`, yêu cầu identity token thường dùng:

~~~text
audience=vault/orders-gce
~~~

Claim `aud` ràng buộc token với đối tượng dự định nhận. JWT cấp cho `vault/another-role` không nên dùng để đăng nhập role `orders-gce`. Claim `exp` đặt thời hạn ngắn cho bằng chứng danh tính; client phải lấy JWT mới nếu cần login lại sau khi JWT cũ hết hạn.

## 3. Điều kiện tiên quyết

Giả sử:

- GCE VM chạy ứng dụng `orders-api` thuộc project `prod-orders-123` tại zone `asia-southeast1-b`.
- Vault API được truy cập tại `https://vault.internal.example:8200`, có DNS đúng và chứng chỉ TLS được JVM tin cậy.
- GCP authentication backend trong Vault được mount tại `auth/gcp`.
- Ứng dụng chỉ cần đọc KV v2 secret `secret/orders/config`.

Trên GCE, VM cần service account gắn phù hợp và có thể gọi metadata server. Không đưa file private key của service account vào ứng dụng để mô phỏng GCE auth. Với các môi trường khác GCE (máy phát triển, Cloud Run hoặc GKE Pod), cơ chế metadata và loại bằng chứng danh tính có thể khác; không mặc định GCE auth sẽ hoạt động tương đương.

Trên Vault, người vận hành cần quyền cấu hình auth method, role và policy; kết nối tới các API Google có thể cần những quyền và cấu hình xác minh phù hợp với phiên bản triển khai. Trước khi chạy lệnh trên production, hãy xác nhận tên tham số role với phiên bản Vault/plugin thực tế.

### GCE auth khác IAM auth

Cùng một Vault GCP authentication method có thể hỗ trợ kiểu **GCE** và **IAM** nhưng cách chứng minh không giống nhau: GCE dựa vào identity JWT có thông tin instance từ metadata; IAM dựa vào quy trình ký/xác minh gắn với danh tính IAM. Nếu ứng dụng chạy trên VM GCE và cần giới hạn theo project, zone hoặc instance, kiểu GCE thường phù hợp. Nếu chạy trong Kubernetes, hãy đánh giá Kubernetes auth hoặc danh tính workload tương ứng thay vì tự suy đoán Pod có identity GCE riêng.

## 4. Cấu hình GCP auth role và Vault policy

### 4.1. Bật auth method

Người quản trị Vault thực hiện:

~~~bash
export VAULT_ADDR="https://vault.internal.example:8200"

# Chỉ enable nếu auth mount gcp chưa tồn tại.
vault auth enable -path=gcp gcp
vault auth list
~~~

Auth method có thể nằm ở mount path khác, ví dụ `auth/gce-prod`. Endpoint login khi đó phải thay tương ứng; tên role và tên mount path là hai thứ độc lập.

### 4.2. Đặt quyền tối thiểu trên KV v2

Tệp policy `orders-read.hcl`:

~~~hcl
path "secret/data/orders/config" {
  capabilities = ["read"]
}
~~~

Nạp policy:

~~~bash
vault policy write orders-read orders-read.hcl
~~~

**Vì sao có `data`?** Khi KV version 2 được mount tại `secret/`, endpoint API đọc bí mật `orders/config` là `secret/data/orders/config`; policy phải khớp đúng đường API. Nếu chỉ cần `read`, đừng cấp thêm `list`, `create`, `update` hoặc quyền trên đường `transit/*`, `pki/*`.

### 4.3. Tạo role GCE ràng buộc project và zone

~~~bash
vault write auth/gcp/role/orders-gce \
  type="gce" \
  policies="orders-read" \
  bound_projects="prod-orders-123" \
  bound_zones="asia-southeast1-b"
~~~

Đây là ví dụ cho role chỉ chấp nhận VM thuộc project/zone chỉ định, rồi phát hành token gắn policy `orders-read`. Nếu nhiều VM hoặc nhiều ứng dụng chạy trong cùng project/zone, nên ràng buộc chặt hơn bằng các điều kiện được plugin hỗ trợ và tách role theo môi trường/workload. Một project rộng không tự đảm bảo phân quyền mức ứng dụng.

Đọc lại role:

~~~bash
vault read auth/gcp/role/orders-gce
vault policy read orders-read
~~~

Khi kiểm tra, quan sát chính sách mà role thực sự gán; đừng chỉ dựa vào tên `orders-read`.

## 5. Lấy GCE identity JWT từ metadata server

Metadata server của GCE có hostname:

~~~text
metadata.google.internal
~~~

Endpoint nhận identity token cho service account mặc định gắn vào VM:

~~~http
GET /computeMetadata/v1/instance/service-accounts/default/identity?audience=vault/orders-gce&format=full
Host: metadata.google.internal
Metadata-Flavor: Google
~~~

- `Metadata-Flavor: Google` là header yêu cầu của metadata server, giúp phân biệt truy vấn chủ động.
- `default` là alias service account trong metadata của VM, không phải tên Vault role.
- `audience=vault/orders-gce` phải thống nhất với role được dùng khi Vault login.
- `format=full` yêu cầu những claim nhận diện instance GCE mở rộng, như project, zone hoặc instance ID, để phục vụ cơ chế xác minh kiểu GCE.

Từ chính VM, thử:

~~~bash
export VAULT_ROLE="orders-gce"

GCE_ID_TOKEN="$(
  curl -fsS --get \
    -H 'Metadata-Flavor: Google' \
    --data-urlencode "audience=vault/$VAULT_ROLE" \
    --data-urlencode 'format=full' \
    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity'
)"

test -n "$GCE_ID_TOKEN" && echo "Nhận được identity JWT"
~~~

Không `echo "$GCE_ID_TOKEN"`, ghi token vào file log hoặc gửi lên trang web giải mã JWT bên ngoài. Nếu cần đọc claim `aud`, `exp`, `iss`, `google.compute_engine.project_id`, `zone`, `instance_id`, thực hiện tại công cụ nội bộ được kiểm soát và loại bỏ giá trị nhạy cảm trước khi ghi log. **Giải mã payload base64 không có nghĩa đã xác minh chữ ký**; Vault phải xác minh token bằng cơ chế tin cậy của chính nó.

### Nếu metadata không phản hồi

Kiểm tra ứng dụng có đang chạy đúng GCE VM không, DNS/route tới `metadata.google.internal`, header yêu cầu, service account gắn vào VM và endpoint identity. Metadata không truy cập được có thể do workload chạy ngoài GCE, chính sách mạng, endpoint sai hoặc môi trường runtime không hỗ trợ; chưa liên quan đến Vault policy. Không dùng JWT tự ký để “đánh lừa” kiểm tra, vì nó không chứng minh danh tính GCE thật.

## 6. Đổi identity JWT lấy Vault token

Endpoint login mặc định:

~~~http
POST /v1/auth/gcp/login
Content-Type: application/json

{
  "role": "orders-gce",
  "jwt": "<identity JWT từ metadata server>"
}
~~~

Phản hồi thành công có đối tượng `auth` với `client_token`, `policies`, `lease_duration` và `renewable` tùy cấu hình. Token Vault này được sử dụng cho các request nghiệp vụ; JWT GCE chỉ là bằng chứng để xác thực.

Ví dụ CLI thử đăng nhập mà **không in bearer token**:

~~~bash
export VAULT_ADDR="https://vault.internal.example:8200"
export VAULT_CA="/etc/vault/ca.pem"

jq -n \
  --arg role "$VAULT_ROLE" \
  --arg jwt "$GCE_ID_TOKEN" \
  '{role: $role, jwt: $jwt}' |
curl -fsS \
  --cacert "$VAULT_CA" \
  -H 'Content-Type: application/json' \
  --request POST \
  --data-binary @- \
  "$VAULT_ADDR/v1/auth/gcp/login" |
jq '{
  has_token: (.auth.client_token != null),
  policies: .auth.policies,
  ttl_seconds: .auth.lease_duration,
  renewable: .auth.renewable
}'

unset GCE_ID_TOKEN
~~~

Dùng `jq --arg` tạo JSON đúng escaping mà không đưa JWT thẳng vào tham số dòng lệnh của HTTP client. Không dùng `curl -v`, bật wire log hoặc lưu toàn bộ phản hồi login: request chứa identity JWT và response chứa Vault token. Trong ứng dụng, nên để `ClientAuthentication` và `SessionManager` phù hợp đảm trách vòng đời credential.

**Nếu auth mount khác mặc định**, chẳng hạn `auth/gce-prod`, endpoint phải là `/v1/auth/gce-prod/login`. Một lỗi 404 trong bước login có thể chỉ là sai route/mount path.

## 7. Tích hợp Spring Cloud Vault và VaultTemplate

### 7.1. Cấu hình xác thực GCE cho Spring Boot

Với ứng dụng dùng **Spring Cloud Vault** hỗ trợ GCE auth:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: vault://
  cloud:
    vault:
      uri: https://vault.internal.example:8200
      authentication: GCP_GCE
      gcp-gce:
        role: orders-gce
      kv:
        enabled: true
        backend: secret
~~~

`spring.config.import: vault://` là cơ chế Config Data trong các phiên bản Spring Boot/Spring Cloud Vault tương ứng; phiên bản cũ có thể dùng bootstrap. Hãy kiểm tra khả năng hỗ trợ `GCP_GCE` và thuộc tính mount path trong chính phiên bản đang sử dụng. JVM cần truststore tin CA của endpoint Vault (có thể cấu hình qua cơ chế SSL của Spring Cloud Vault hoặc HTTP client thực tế).

Cấu hình trên là ví dụ cho Spring Cloud Vault. Nếu tạo thủ công `VaultTemplate` bằng `spring-vault-core`, cần cung cấp đúng `ClientAuthentication`, `RestOperations`/HTTP client và `SessionManager`. Không mặc định rằng `spring.cloud.vault.*` sẽ tự thay đổi một `VaultTemplate` tự dựng.

### 7.2. Java đọc KV v2 bằng VaultTemplate

Sau khi xác thực, một service có thể dùng:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersConfigurationReader {

    private final VaultTemplate vaultTemplate;

    public OrdersConfigurationReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public Map<String, Object> readConfiguration() {
        VaultResponse response = vaultTemplate
                .opsForKeyValue("secret", KeyValueBackend.KV_2)
                .get("orders/config");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Secret orders/config not found");
        }

        return response.getData();
    }
}
~~~

Với `KV_2`, Spring Vault xử lý định dạng API KV v2; policy ở Vault vẫn cần cho phép `read` trên `secret/data/orders/config`. Nếu ứng dụng chỉ cần Transit encrypt thì policy nên cấp `update` trên `transit/encrypt/<key-name>`, không cấp cả decrypt khi không có nhu cầu. Tương tự, PKI cần giới hạn quyền issue và TTL theo role phát hành.

**Quan trọng:** ví dụ Java không lấy JWT từ metadata bằng tay. Việc đó do thành phần authentication của Spring Vault/Spring Cloud Vault thực hiện. Đừng đưa token vào biến static, trả secret ra endpoint công khai hoặc in response Vault ra log.

## 8. Token, lease và thay đổi vòng đời VM

Identity JWT GCE, Vault token, KV dynamic lease và PKI certificate có thời hạn/điều kiện gia hạn riêng:

| Thành phần | Hết hạn thì sao? | Xử lý đúng |
| --- | --- | --- |
| GCE identity JWT | Không dùng JWT đã hết hạn để đăng nhập mới. | Xin identity JWT mới từ metadata. |
| Vault client token | Không còn quyền gọi Vault sau khi token không hợp lệ. | Renew nếu được phép hoặc login lại bằng identity JWT mới. |
| Dynamic secrets lease | Credential động đến hạn hoặc bị revoke. | Renew/revoke/cấp mới tùy engine. |
| PKI certificate | Chứng chỉ qua `notAfter` không còn hợp lệ. | Phát hành/luân chuyển chứng chỉ theo chính sách PKI. |

Một Vault token đang còn hiệu lực không nhất thiết hết hạn cùng lúc với JWT đã dùng để tạo ra nó. Ngược lại, một JWT còn hạn không đảm bảo Vault token sẽ được cấp: instance phải khớp role và các chính sách Vault hiện tại.

Đối với managed instance group, VM được thay mới có thể có `instance_id` và `instance_creation_timestamp` khác. Nếu role bị ràng buộc quá chặt vào instance cũ, VM mới có thể bị từ chối. Cần thiết kế ràng buộc tương thích quy trình rollout, đồng thời có cách thu hồi Vault token/ủy quyền cũ nếu workload không còn được phép.

## 9. Chẩn đoán lỗi theo từng tầng

| Dấu hiệu | Tầng | Cần kiểm tra |
| --- | --- | --- |
| `UnknownHostException: metadata.google.internal` | Metadata/DNS | Ứng dụng có chạy trên GCE, DNS/route metadata đúng không? |
| Metadata 403/404 hoặc trả lỗi tham số | Metadata | Endpoint, `Metadata-Flavor`, service account, audience và môi trường. |
| Identity JWT nhận được nhưng login báo invalid JWT/audience | Vault GCP auth | `aud=vault/<role>`, thời hạn, issuer, chữ ký, clock skew và đúng role. |
| Login từ chối do bound constraints | Vault role | Project, zone, instance/service account và giá trị cấu hình role. |
| `404 no handler for route` khi login | Vault routing | GCP auth đã enable chưa, mount path có đúng không? |
| `Connection refused`, timeout | DNS/TCP/mạng | Vault API hostname/port, route, firewall, listener và backend. |
| `SSLHandshakeException`, `PKIX path building failed` | TLS/JVM | CA trong truststore, hostname SAN, TLS của HTTP client Java. |
| `/auth/gcp/login` thành công nhưng `KV read` 403 | Vault policy | Policy của Vault token, KV v1/v2, đường dẫn `data` và capabilities. |
| Sau một thời gian mới 403/token expired | Phiên/token | TTL, renewal/reauth, SessionManager, thay VM và quyền hiện tại. |

**Không trộn các nguyên nhân:** metadata lỗi xảy ra *trước login*; TLS lỗi xảy ra *trước HTTP login Vault*; GCP auth từ chối xảy ra *trước khi nhận Vault token*; KV 403 xảy ra *sau login*. Cách sửa cho mỗi loại khác nhau.

### Các lệnh kiểm tra từ chính GCE VM

~~~bash
# Metadata server: chỉ kiểm tra kết nối, không in identity token.
curl -fsS -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/id' \
  -o /dev/null && echo "metadata reachable"

# Vault: lần lượt thử DNS, TCP và TLS/HTTP.
getent ahosts vault.internal.example
nc -vz -w 3 vault.internal.example 8200

curl -sS --cacert /etc/vault/ca.pem \
  -o /dev/null \
  -w 'http_status=%{http_code}\n' \
  'https://vault.internal.example:8200/v1/sys/health'
~~~

Endpoint `/v1/sys/health` có thể trả mã khác 200 khi Vault standby, sealed hoặc chưa khởi tạo; lúc đó đã có kết nối HTTP, cần đọc trạng thái Vault và đường đi qua load balancer. Nếu client JVM vẫn báo lỗi dù curl hoạt động, đối chiếu truststore, proxy và HTTP client mà Java thực sự sử dụng.

Khi log lỗi, chỉ ghi loại lỗi, đường dẫn API không nhạy cảm, thời điểm và correlation ID. Tránh ghi bearer token, request body login, response token, secret value hay private key.

## 10. Các tình huống thực hành

### Tình huống A: Spring Vault GCP_GCE chạy trên laptop

Ứng dụng cấu hình `GCP_GCE` nhưng local không truy cập được `metadata.google.internal`. Vấn đề nằm ở môi trường không có identity GCE. Unit test nên mock `ClientAuthentication` hoặc lớp giao tiếp metadata; integration test thật phải chạy trên GCE staging với role staging. Không đặt token production trong file cấu hình local.

### Tình huống B: JWT hợp lệ nhưng VM sai zone

Vault role `orders-gce` chỉ cho `asia-southeast1-b`, trong khi VM mới ở `asia-southeast1-a`. Metadata vẫn cấp JWT hợp lệ, nhưng role có quyền từ chối nó. Kiểm tra claim GCE từ JWT đã xác minh và đối chiếu role. Sửa triển khai/role theo chính sách chấp thuận, không bỏ mọi ràng buộc chỉ để hết lỗi.

### Tình huống C: Vault login được, đọc KV v2 thất bại

Vai trò gắn policy `orders-read`, nhưng policy được viết nhầm `secret/orders/config`. API KV v2 thực sự đọc `secret/data/orders/config`; Vault trả 403. Sửa đúng path và test lại quyền, không mở rộng policy toàn bộ `secret/*`.

### Tình huống D: Thay VM, lỗi token xuất hiện sau vài phút

JWT mới có thể được lấy từ metadata, nhưng Vault token cũ có TTL và lịch renew riêng; hoặc client tái xác thực thất bại khi instance mới không còn khớp role. Tách lỗi token renewal với lỗi lấy GCE JWT và lỗi đăng nhập; kiểm tra `SessionManager`/TTL cùng log đã lọc, rồi chạy rollout test.

## 11. Kiểm thử tích hợp và vận hành an toàn

Thiết kế kiểm thử theo lớp:

| Cấp kiểm thử | Cách triển khai | Phạm vi chứng minh |
| --- | --- | --- |
| Unit | Mock metadata/auth adapter hoặc `ClientAuthentication` và `VaultTemplate`. | Logic request, mapping, timeout và xử lý lỗi của Java. |
| Vault integration | Vault test instance với KV v2/policy và cơ chế auth kiểm soát được. | Đường secret engine, API, quyền và mapping của Spring Vault. |
| GCE end-to-end | VM GCE staging thật, metadata thật, Vault GCP auth role staging. | JWT do Google ký được Vault chấp nhận, binding đúng và ứng dụng nhận quyền. |
| Negative test | Sai project/zone, audience sai, JWT hết hạn, CA sai, policy thiếu read. | Từng lớp từ chối đúng, không vô tình cấp quyền. |
| Resilience | Token hết hạn, Vault failover, certificate rotation, VM replacement. | Khả năng renew/reauth, timeout, retry có giới hạn và quan sát lỗi. |

**Không dùng một JWT tự ký để tuyên bố đã kiểm thử thành công GCE auth.** Mock giúp kiểm thử ứng dụng, còn kiểm chứng chữ ký Google/instance binding cần GCE/Vault thật hoặc hạ tầng tương đương được cấu hình hợp lệ.

Vận hành production cần:

- **Bảo vệ metadata:** hạn chế quyền thực thi trên VM, phòng SSRF và kiểm soát workload nào có thể truy cập identity endpoint. Không cần service account JSON key nếu GCE metadata identity đáp ứng yêu cầu.
- **Phân tách quyền:** quyền Google IAM trên service account và Vault policy là hai hệ quyền khác nhau; dùng mức tối thiểu cho cả hai.
- **Theo dõi lỗi:** metadata failure, GCP login denial, token renew/reauth, Vault 403 và latency; loại bỏ token, JWT, secret khỏi logs/metrics/traces.
- **Bảo vệ Vault TLS:** tin CA đúng, kiểm tra hostname/SAN, xoay cert có kiểm thử; không tắt TLS validation để chữa lỗi GCE auth.
- **Giới hạn retry:** metadata hoặc mạng có thể lỗi tạm thời, nhưng `invalid JWT`, binding mismatch và permission denied cần chẩn đoán cấu hình, không retry vô hạn.

## 12. Câu hỏi tự kiểm tra

1. Identity JWT từ metadata chứng minh điều gì? Nó có thay Vault token để gọi `/v1/secret/data/orders/config` được không?
2. Vì sao `audience=vault/orders-gce` cần khớp với Vault role tại thời điểm login?
3. Nếu VM đã đăng nhập Vault thành công nhưng `VaultTemplate` đọc KV v2 bị 403, cần xem loại policy path nào?
4. Tại sao thay đổi zone của VM có thể làm GCE auth thất bại ngay cả khi Google vẫn cấp JWT hợp lệ?
5. JWT GCE hết hạn có làm Vault token đang còn TTL tự động hết hạn ngay không? Khi nào cần lấy JWT mới?
6. Nếu chuyển workload từ GCE VM sang GKE Pod, điều gì phải đánh giá lại về cách chứng minh danh tính cloud?

**Ghi nhớ:** GCE metadata cung cấp **bằng chứng danh tính máy ảo**, Vault GCP/GCE auth xác minh nó bằng **role constraints**, Vault phát hành **client token**, và **policy** quyết định khả năng đọc KV, dùng Transit hay PKI. Tách biệt bốn bước này là nền tảng để triển khai Spring Vault an toàn và xử lý sự cố chính xác.
