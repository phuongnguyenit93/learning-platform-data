# Xác thực ứng dụng với Vault và phân quyền truy cập dữ liệu

> **Chương:** Bản đồ Spring Vault  
> **Phạm vi:** Thiết kế cách ứng dụng Spring/Java chứng minh danh tính với HashiCorp Vault, nhận token có giới hạn quyền và sử dụng `VaultTemplate`/`VaultOperations` để truy cập đúng secret hoặc thao tác mà workload được phép.

## Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Phân biệt **authentication (xác thực)**, **authorization (phân quyền)**, **workload identity**, **Vault token**, **auth role** và **policy**.
2. Giải thích luồng đăng nhập Vault từ Kubernetes ServiceAccount/JWT, AppRole hoặc danh tính cloud, cùng bài toán bootstrap ban đầu.
3. Thiết kế chính sách Vault theo nguyên tắc **quyền tối thiểu**, nhất là với KV v2, Database, Transit và PKI.
4. Hiểu nơi `ClientAuthentication`, `SessionManager` và `VaultOperations` tham gia vào ứng dụng Spring.
5. Đọc một ví dụ cấu hình auth theo workload, triển khai Java đọc KV v2 và xác định chính xác lỗi quyền theo API path.
6. Đề xuất cách quản lý TTL/rotation/revocation, giám sát và kiểm thử tích hợp, bao gồm các bài thử **bị từ chối**.

## 1. Đăng nhập thành công chưa có nghĩa được đọc mọi secret

Xét hai ứng dụng Spring Boot chạy trên Kubernetes:

- `orders-service` cần API key thanh toán ở KV v2 và được phép **mã hóa** dữ liệu khách hàng bằng Transit.
- `fraud-service` cần **giải mã** một loại dữ liệu cụ thể để phục vụ rà soát gian lận, nhưng không cần API key thanh toán.

Nếu cả hai dùng chung một Vault token có quyền quản trị, bất kỳ service nào bị lộ token cũng có thể lấy bí mật của service còn lại. Vault giúp tránh điều đó khi danh tính và quyền được cấu hình đúng.

Có hai câu hỏi độc lập:

- **Authentication:** “Đây có đúng workload được khai báo không?” Vault kiểm tra bằng chứng danh tính qua **auth method**, rồi cấp Vault token theo role và những ràng buộc tương ứng.
- **Authorization:** “Token của workload này có được `read` hoặc `update` trên **API path** đang gọi không?” Vault kiểm tra policy ở mỗi yêu cầu.

~~~mermaid
flowchart LR
    K["orders-service<br/>danh tính workload"] -->|"Bằng chứng danh tính"| A["Vault auth method<br/>Kubernetes / AppRole / JWT / cloud"]
    A -->|"Đăng nhập hợp lệ"| T["Vault token<br/>TTL + policies"]
    T --> R{"ACL policy:<br/>path + capability?"}
    R -->|"Được phép"| E["Secrets engine<br/>KV / Database / Transit / PKI"]
    R -->|"Từ chối"| F["HTTP 403<br/>permission denied"]
    E --> O["Response cho client"]
~~~

**Spring Vault** giúp ứng dụng Java gửi request đăng nhập và các yêu cầu tới Vault. **HashiCorp Vault server** mới là nơi xác thực, cấp token, áp policy và thực thi secrets engines. Thư viện Java không tự quyết định policy chỉ vì developer đã gọi đúng hàm.

## 2. Các khái niệm trong mô hình danh tính của Vault

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Workload identity** | Danh tính có thể chứng minh của process/pod/job | Kubernetes ServiceAccount `orders-sa` trong namespace `commerce` |
| **Auth method** | Cách Vault xác minh danh tính ban đầu | `auth/kubernetes`, `auth/approle`, JWT hoặc cloud IAM |
| **Auth role** | Quy tắc ánh xạ danh tính hợp lệ sang cấu hình token và policies | Role `orders-role` chỉ nhận ServiceAccount/namespace được chọn |
| **Vault token** | Credential được client gửi trong những lời gọi Vault tiếp theo | Token có TTL, capabilities suy ra từ policy |
| **Policy** | Danh sách ACL path và các hành động được phép/từ chối | `read` một key KV v2, `update` một endpoint Transit encrypt |
| **Secrets engine** | Thành phần phục vụ dữ liệu/chức năng sau khi vượt kiểm tra quyền | KV, Database, Transit, PKI |
| **Lease** | Vòng đời của một secret động được cấp nếu engine hỗ trợ | Credential PostgreSQL cấp 15 phút |
| **Audit device** | Ghi nhận truy cập/API theo cấu hình phía Vault | Audit file/socket và hệ thống lưu audit được kiểm soát |

**Role của auth method** không giống **database role**: role Kubernetes quyết định token nào được cấp và với policies nào; role Database secrets engine quyết định cách cấp credential cho hệ DB, thời hạn và phạm vi quyền SQL.

**Policy** không phải một password và không cần gửi cùng mọi request; policy được cấu hình ở Vault và gắn với token/danh tính phù hợp. Ứng dụng gửi token, Vault đánh giá quyền theo token đó.

### 2.1. Spring Security và Vault auth bảo vệ hai biên khác nhau

~~~text
Người dùng cuối
    |
    | Access token/session để gọi REST API
    v
Spring Security --> OrderController --> OrdersService
                                          |
                                          | Vault token của workload
                                          v
                                     Spring Vault
                                          |
                                          v
                                HashiCorp Vault server
~~~

JWT của người dùng cuối dùng để quyết định họ có được xem/tạo đơn hàng không. Danh tính của `orders-service` dùng để quyết định service được truy cập Vault path nào. Không tự chuyển JWT người dùng cuối thành `X-Vault-Token`, cũng không coi quyền `ROLE_ADMIN` trong ứng dụng là quyền quản trị Vault.

Nếu cần phân quyền từng người dùng đối với Vault, đó là một thiết kế ủy quyền riêng có ràng buộc danh tính và audit; không tự xuất hiện chỉ bằng cách inject `VaultTemplate`.

## 3. Bài toán bootstrap: lấy quyền truy cập Vault từ đâu?

Đặt một Vault root token vào `application.yml` chỉ chuyển chỗ lưu bí mật. Kẻ có quyền đọc Git/image/CI logs vẫn có thể lấy token, và token có quyền quá rộng sẽ mở rộng tác động sự cố.

Thiết kế theo workload identity thường đi qua các bước:

1. Hạ tầng cấp bằng chứng danh tính cho workload, ví dụ ServiceAccount JWT được mount vào pod hoặc thông tin IAM.
2. Spring Vault hoặc lớp tích hợp tương ứng dùng bằng chứng này để đăng nhập auth method đã cấu hình trên Vault.
3. Vault kiểm tra bằng chứng, các điều kiện role và trust configuration; nếu hợp lệ, Vault phát token có TTL/policies.
4. `SessionManager` dùng Vault token cho các request đến KV/Database/Transit/PKI theo cách được cấu hình.
5. Vault tiếp tục kiểm tra quyền với **từng API path**; token hợp lệ có thể vẫn nhận `403` trên path không được phép.

### 3.1. Những phương thức xác thực thường gặp

| Auth method | Bằng chứng ban đầu | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|---|
| **Kubernetes** | ServiceAccount JWT của pod | Ứng dụng chạy trong Kubernetes | Namespace/ServiceAccount binding, token audience, issuer/TokenReview, TTL |
| **JWT/OIDC** | JWT từ nhà phát hành danh tính đáng tin cậy | Workload có JWT được ký/kiểm chứng chuẩn | Issuer, JWKS/signing keys, audience, claims bound vào role |
| **Cloud IAM** | Danh tính workload của nền tảng cloud | VM/container có danh tính cloud đủ tin cậy | Trust relationship, role mapping, phạm vi quyền của tài nguyên cloud |
| **AppRole** | `RoleID` và `SecretID` theo cấu hình | Job/máy chủ ngoài môi trường có identity federation thuận lợi | Bảo vệ SecretID, TTL/số lượt sử dụng, CIDR, response wrapping nếu cần |
| **Client certificate** | Khóa riêng/chứng chỉ client được Vault tin | Có PKI và cơ chế phân phối chứng chỉ cho workload | Private key, CA trust, cert TTL, chính sách auth role |
| **Token đã cấp trước** | Vault token | Thực hành cục bộ/công cụ vận hành có kiểm soát | Không nhúng root token; TTL và quyền tối thiểu |

Không có phương thức nào “tự an toàn” nếu bên phát hành identity, role mapping hoặc kênh cấp phát bị cấu hình lỏng. Chọn theo môi trường và mô hình tin cậy, không chỉ theo số dòng Java cần viết.

### 3.2. Kubernetes ServiceAccount là danh tính workload, không phải mật khẩu hệ DB

Ví dụ:

~~~text
Kubernetes namespace: commerce
ServiceAccount:       orders-sa
Pod:                  orders-service-...
Vault auth mount:     auth/kubernetes/
Vault auth role:      orders-role
Vault policy:         orders-policy
Vault KV v2 mount:    secret/
KV key logic:         prod/orders/payment
~~~

Một ServiceAccount JWT của `orders-sa` được dùng làm bằng chứng để login; Vault kiểm tra role `orders-role` có cho namespace/ServiceAccount đó hay không. Vault token trả về dùng để đọc API path theo `orders-policy`; JWT ban đầu **không** phải mật khẩu PostgreSQL hay API key của đối tác.

Trên Kubernetes hiện đại, projected ServiceAccount token có thể thay đổi theo thời gian, chứa `aud` và có ngày hết hạn. Cấu hình Vault phải tương thích với issuer/audience và cơ chế TokenReview; client cần đọc nguồn token hiện hành thay vì giả định file sẽ chứa một JWT bất biến suốt vòng đời pod.

### 3.3. AppRole vẫn có một secret phải bảo vệ

Với AppRole, `RoleID` xác định role và `SecretID` thường là bằng chứng bí mật bổ sung để login. Nếu hard-code `SecretID` cùng source code hoặc image, bạn chưa giải quyết được khâu cấp phát danh tính. Cần cơ chế bảo vệ/phân phối SecretID, cân nhắc response wrapping, TTL, giới hạn số lượt sử dụng và quyền cấp phát. AppRole có thể phù hợp với batch/VM, nhưng cần thiết kế bootstrap đầy đủ.

## 4. Luồng xác thực Kubernetes từ pod đến Vault

~~~mermaid
sequenceDiagram
    autonumber
    participant P as orders-service pod
    participant SV as Spring Vault client
    participant V as Vault Kubernetes auth
    participant K as Kubernetes API/identity
    participant ACL as Vault policy + KV v2

    P->>SV: Cung cấp ServiceAccount JWT
    SV->>V: POST /v1/auth/kubernetes/login<br/>role=orders-role, jwt=...
    V->>K: Xác minh JWT/TokenReview<br/>theo cấu hình auth
    K-->>V: Kết quả xác minh danh tính
    V->>V: Kiểm tra role ràng buộc SA/namespace
    V-->>SV: Vault token + TTL + policies
    SV->>ACL: GET /v1/secret/data/prod/orders/payment<br/>X-Vault-Token
    alt Token có read trên path
        ACL-->>SV: 200 + KV data
    else Token thiếu quyền hoặc không hợp lệ
        ACL-->>SV: 403 permission denied
    end
    SV-->>P: Kết quả hoặc lỗi để ứng dụng xử lý
~~~

Điều kiện để sơ đồ hoạt động:

- Vault server có auth mount Kubernetes được cấu hình đúng Kubernetes API, chứng chỉ tin cậy và phương thức xác minh token theo phiên bản đang dùng.
- Role `orders-role` ràng buộc đúng ServiceAccount, namespace và audience nếu cấu hình/loại JWT yêu cầu.
- Workload thực sự chạy bằng `orders-sa`, có projected token hợp lệ và có đường mạng/TLS tới Vault.
- Role gán policy chỉ cấp những thao tác cần dùng; secrets engine đã được mount và chứa dữ liệu phù hợp.
- Ứng dụng không log nội dung ServiceAccount JWT, Vault token hoặc response có secret.

### 4.1. Ví dụ cấu hình phía Vault

Giả sử auth method, kết nối Kubernetes và KV v2 mount `secret/` đã được quản trị viên cấu hình, và `orders-policy.hcl` chứa policy hợp lệ. Một ví dụ gán role:

~~~bash
# Lệnh ví dụ thực hiện bởi người quản trị trong môi trường test.
vault policy write orders-policy orders-policy.hcl

vault write auth/kubernetes/role/orders-role \
  bound_service_account_names=orders-sa \
  bound_service_account_namespaces=commerce \
  policies=orders-policy \
  ttl=1h
~~~

Không chạy lại role command một cách mù quáng trên production: role có thể đang dùng thêm `audience`, token parameters hoặc giới hạn khác cần giữ. Khi dùng ServiceAccount JWT có audience dành riêng cho Vault, phải cấu hình audience của token và role tương ứng. Ví dụ chỉ tập trung vào quan hệ **Kubernetes identity → Vault role → Vault policy**.

Nếu auth method được mount ở path khác `auth/kubernetes/`, login path và cấu hình client phải điều chỉnh theo mount thực tế.

## 5. Policy Vault: hành động nào trên API path nào?

Vault ACL policy thường được mô tả bằng HCL, gồm một hoặc nhiều khối `path` với `capabilities`. Khi nhận request, Vault đối chiếu token với quyền trên đường dẫn API tương ứng.

### 5.1. Những capability thường dùng

| Capability | Mục đích thường gặp | Ví dụ |
|---|---|---|
| `read` | Đọc dữ liệu/metadata từ endpoint hỗ trợ đọc | GET một KV v2 secret, GET Database credentials |
| `create` | Tạo dữ liệu tại endpoint phù hợp | Tạo key mới qua API hỗ trợ tạo |
| `update` | Ghi/cập nhật hoặc gọi thao tác qua POST/PUT | Transit encrypt/decrypt, PKI issue |
| `delete` | Xóa tại endpoint tương ứng | Xóa theo API của engine |
| `list` | Liệt kê các key/path khi endpoint hỗ trợ | KV v2 metadata listing |
| `sudo` | Thêm quyền cho một số endpoint Vault đặc quyền | Dành cho quản trị cụ thể, không cấp đại trà |
| `deny` | Chặn quyền tại path | Loại trừ truy cập, có thứ tự ưu tiên theo luật ACL |

Không suy luận capability chỉ từ tên HTTP method trong mọi trường hợp. Ví dụ Transit encrypt thường gọi `POST` và yêu cầu capability `update`; muốn biết chính xác cần đối chiếu API và chính sách của endpoint. `read` trên đường dẫn encrypt không tự cho phép mã hóa.

### 5.2. KV v2: phân biệt mount, key logic và ACL path

Ví dụ cấu hình:

~~~text
Vault address:     https://vault.internal.example:8200
KV v2 mount:       secret/
Key logic:         prod/orders/payment
Java API:          opsForKeyValue("secret", KV_2).get("prod/orders/payment")
HTTP API read:     GET /v1/secret/data/prod/orders/payment
Vault ACL path:    secret/data/prod/orders/payment
HTTP API list:     LIST /v1/secret/metadata/prod/orders/
~~~

Một lỗi rất thường gặp: policy cấp `read` cho `secret/prod/orders/payment` trong khi request KV v2 thực sự đi vào `secret/data/prod/orders/payment`. Thêm `data/` đúng ở **policy path** hoặc khi tự gọi HTTP/raw API; **không** thêm `data/` vào đối số key logic của `opsForKeyValue(..., KV_2).get(...)`.

### 5.3. Policy quyền tối thiểu cho orders-service

~~~hcl
# Quyền đọc đúng một key KV v2.
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}

# Orders chỉ mã hóa với khóa Transit đã cấu hình.
path "transit/encrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Policy trên không cấp quyền:

- Liệt kê các key KV (`list` trên `secret/metadata/...`).
- Đọc secret của `fraud-service` hoặc service khác.
- Ghi, xóa hoặc destroy version KV.
- Gọi `transit/decrypt/orders-pii`.
- Tạo Vault policy, đổi auth method hoặc quản lý root token.

Nếu `fraud-service` thực sự cần giải mã, hãy tạo role/policy riêng cho workload đó:

~~~hcl
path "transit/decrypt/orders-pii" {
  capabilities = ["update"]
}
~~~

Việc này tạo ra ranh giới quyền thực tế: chiếm quyền `orders-service` không tự đem lại quyền giải mã, trừ khi còn một đường quyền khác trong policy, role hoặc hạ tầng.

### 5.4. Quyền Vault khác quyền trên hệ thống đích

Với Database secrets engine, policy cho một ứng dụng xin credential có thể là:

~~~hcl
path "database/creds/orders-reader" {
  capabilities = ["read"]
}
~~~

Điều này chỉ cho phép ứng dụng xin credential từ engine role `orders-reader`. **Quyền SELECT/INSERT/UPDATE trong PostgreSQL** do cấu hình role của Database engine và quyền SQL trên database quyết định. Vault policy không thay thế kiểm soát quyền của hệ thống đích.

Với PKI, quyền `update` trên `pki/issue/orders-client` hoặc `pki/sign/orders-client` cho phép yêu cầu phát hành/ký theo role; danh tính, SAN/domain và TTL của certificate phải tiếp tục được hạn chế bởi PKI role tương ứng.

### 5.5. Wildcard, quyền liệt kê và phạm vi quá rộng

Không mặc định viết:

~~~hcl
# Ví dụ PHẢN MẪU: trao quá nhiều quyền cho service nghiệp vụ.
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
~~~

Một policy rộng có thể cho ứng dụng đọc/sửa nhiều secret không thuộc chức năng của nó. Ngay cả quyền `list` trên KV v2 metadata cũng có thể làm lộ **tên** của những key nhạy cảm. Dùng path cụ thể hoặc nhánh có chủ đích, tách môi trường, tách service, và kiểm tra cả những policy khác được gắn vào token (bao gồm `default` nếu có).

Chú ý: Vault có quy tắc khớp đường dẫn, wildcard và độ ưu tiên policy riêng; `deny` có ý nghĩa ưu tiên khi xác định quyền. Đừng phỏng đoán hiệu quả từ việc nhìn một khối HCL đơn lẻ: hãy thử quyền bằng token thực của từng workload.

## 6. Spring Vault gắn danh tính và token vào HTTP request ra sao?

Ở ứng dụng Spring, ba interface/thành phần đáng nhớ:

| Thành phần Spring Vault | Vai trò |
|---|---|
| `ClientAuthentication` | Xác định cách lấy Vault token từ bằng chứng danh tính |
| `SessionManager` | Cung cấp token cho các lời gọi, hỗ trợ chiến lược sử dụng/gia hạn token theo triển khai |
| `VaultOperations` / `VaultTemplate` | Cung cấp thao tác đọc/ghi/engine bằng API Java và gửi request tới Vault |

~~~mermaid
flowchart TB
    B["OrderService<br/>Java business logic"] --> O["VaultOperations<br/>VaultTemplate"]
    O --> S["SessionManager"]
    S --> A["ClientAuthentication<br/>Kubernetes/JWT/AppRole/..."]
    O --> H["HTTP client + TLS"]
    A -->|"Login request khi cần"| V["Vault server auth method"]
    V -->|"Token + TTL + policies"| S
    H -->|"GET/POST + X-Vault-Token"| P["Vault policy + secrets engine"]
    P -->|"JSON response hoặc lỗi"| O
~~~

`VaultTemplate` chạy trong JVM của ứng dụng, Vault server chạy ở hạ tầng riêng. Client nhận token rồi sử dụng token cho request tiếp theo (thường qua header `X-Vault-Token`). Không tự ghi token vào log, HTTP trace có phạm vi truy cập rộng hoặc exception cho người dùng.

### 6.1. Cấu hình xác thực Kubernetes trong Spring Cloud Vault

Nếu dự án dùng **Spring Cloud Vault** để tích hợp Vault vào hệ thống cấu hình Spring Boot, một mẫu cấu hình theo workload là:

~~~yaml
# Ví dụ minh họa: cần starter tương thích và Vault/Kubernetes đã cấu hình.
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-role
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
~~~

Tính khả dụng và cách hoạt động của các property phụ thuộc nhánh Spring Boot/Spring Cloud Vault đang dùng. Cần cấu hình CA trust, auth mount path, context/mount secrets, role và policies ở Vault; một file YAML như trên không tự tạo những thành phần đó.

**Spring Vault** thuần thích hợp cho code gọi `VaultOperations` chủ động; **Spring Cloud Vault** chuyên tích hợp các key Vault vào `Environment` và nguồn cấu hình. Spring Cloud Vault sử dụng các cơ chế client của hệ sinh thái Spring Vault nhưng việc nạp config và refresh không đồng nghĩa credential trong datasource/HTTP client tự thay khi token hoặc secret hết hạn.

### 6.2. Ví dụ Java: truy cập KV v2 sau khi client đã xác thực

Giả sử ứng dụng đã có bean `VaultOperations` sử dụng workload authentication phù hợp (tự cấu hình hoặc qua tích hợp tương thích). Code nghiệp vụ chỉ yêu cầu key logic:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersPaymentSecret {

    private final VaultKeyValueOperations kv;

    public OrdersPaymentSecret(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
            "secret", KeyValueBackend.KV_2);
    }

    public String loadApiKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Required payment secret is absent");
        }

        Object value = response.getRequiredData().get("api-key");
        if (!(value instanceof String apiKey) || apiKey.isBlank()) {
            throw new IllegalStateException("Required payment field is absent");
        }
        return apiKey;
    }
}
~~~

`kv.get("prod/orders/payment")` sẽ cần `read` trên `secret/data/prod/orders/payment` khi mount `secret/` là KV v2. Code **không** được quyền hơn policy chỉ vì đã inject bean. Khi bị Vault từ chối, phải phân loại lỗi và kiểm tra auth role/token/path; không thêm “fallback” sang root token.

Code minh họa không trình bày cache, rotation hoặc bảo vệ API key trong client gọi đối tác. Các trách nhiệm đó nằm tại ứng dụng dù Vault cấp quyền đọc thành công.

### 6.3. Trường hợp token thử nghiệm được cấp sẵn

Để hiểu sự phân tách, có thể đăng ký `ClientAuthentication` dùng token thử nghiệm lấy từ bên ngoài:

~~~java
import java.util.Objects;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;

ClientAuthentication clientAuthentication = new TokenAuthentication(
    Objects.requireNonNull(System.getenv("VAULT_TOKEN")));
~~~

Đây là mẫu tối giản để học API, **không phải hướng khuyến nghị cho workload production**. Người vận hành phải bảo vệ nguồn cấp token; môi trường process không tự mã hóa token. Với Kubernetes/JWT/AppRole/cloud, chọn implementation `ClientAuthentication` tương ứng và kiểm tra API của phiên bản Spring Vault triển khai.

## 7. Vòng đời token và việc đổi secret

Vault token được cấp với policy và TTL nhất định. Nếu token renewable, client có thể gia hạn theo giới hạn server cho phép; nếu không hoặc token đã bị revoke, client phải có chiến lược xác thực lại hoặc thất bại có kiểm soát.

| Đối tượng | Thời hạn/luân chuyển nằm ở đâu? | Ứng dụng cần xử lý |
|---|---|---|
| **ServiceAccount JWT/identity** | Kubernetes/identity provider | Đọc bằng chứng còn hợp lệ, không cache JWT đã hết hạn |
| **Vault token** | Vault auth/token, TTL/renewability/policy | `SessionManager` quản lý token theo khả năng; login lại hoặc fail khi bị thu hồi |
| **KV v2 API key tĩnh** | KV version và **bên phát hành** API key | Làm mới giá trị ứng dụng dùng; phối hợp revoke key cũ với đối tác |
| **Database credential động** | Database engine/lease và DB | Gia hạn/cấp mới khi được phép; chuyển connection pool |
| **Transit key** | Transit key versions và policy | Thiết kế rewrap/re-encrypt, phân tách quyền encrypt/decrypt |
| **PKI certificate** | PKI role và thời hạn X.509 | Cấp lại, thay certificate/private key trong TLS context |

Đặc biệt, **Vault token TTL khác lease TTL** của Database credential. Một `SessionManager` gia hạn token không có nghĩa Hibernate/HikariCP dùng account DB cũ được kéo dài hạn sử dụng. Spring Vault có `SecretLeaseContainer` hỗ trợ theo dõi/gia hạn/rotation secret có lease theo cấu hình, nhưng code của ứng dụng vẫn phải thay credential trong datasource/client tương ứng.

### 7.1. Hai kiểu quản lý phiên

- `SimpleSessionManager` không có lịch quản lý gia hạn/thu hồi token theo vòng đời như session manager nâng cao.
- `LifecycleAwareSessionManager` hỗ trợ lifecycle của login token, có thể lên lịch renewal khi điều kiện cho phép và xử lý đóng phiên.

Không mặc định mọi token đều renewable, mọi auth method đều trả token cùng đặc tính hoặc một phiên Spring Vault có thể gia hạn vô hạn. Hãy thử thời điểm token hết hạn, role/policy thay đổi và trường hợp Vault không liên lạc được.

### 7.2. Token bị lộ hoặc workload bị chiếm quyền

Khi nghi ngờ token lộ, ưu tiên vô hiệu hóa token/quyền theo quy trình sự cố, kiểm tra audit và các secret mà token có thể đọc/cấp. Việc revoke token có thể ảnh hưởng các lease liên quan, song bí mật tĩnh đã lấy ra hoặc đã gửi tới đối tác vẫn có thể tồn tại ngoài Vault. Nếu API key bị lấy khỏi KV, cần phối hợp **thu hồi API key tại nhà phát hành**; revoke Vault token một mình không làm key đó mất hiệu lực.

## 8. Những lỗi thường gặp khi tích hợp ứng dụng và policy

| Triệu chứng | Vùng cần kiểm tra | Gợi ý |
|---|---|---|
| Login Kubernetes thất bại | Vault auth config/role, JWT, Kubernetes identity | Kiểm tra ServiceAccount, namespace, audience, trust/TokenReview, auth mount |
| Token hợp lệ nhưng đọc KV trả 403 | ACL policy trên path thực, policies gắn với token | KV v2 cần `secret/data/...`; kiểm tra capability `read` |
| 403 dù đã sửa policy | Token hiện có, role mapping, path hoặc deny policy | Xác nhận token thực đang dùng, hiệu lực thay đổi policy, quyền tổng hợp và precedence |
| Liệt kê key bị từ chối dù đọc key được | KV v2 metadata policy | `list` tại `secret/metadata/...` là quyền riêng, chỉ cấp khi cần |
| GET secret trả 404 | Mount/key logic, version, KV v1/v2 | Đối chiếu mount và path, phân biệt với 403 |
| Token hết hạn/revoked | TTL, session manager, bằng chứng identity | Re-login/renew khi hợp lệ; không retry vô hạn bằng token chết |
| TLS handshake failed | HTTP/TLS/CA trust | Sửa truststore và tên máy/certificate, không bỏ xác minh TLS |
| Transit encrypt bị từ chối | Capability/path/role của Transit | Kiểm tra `update` tại `transit/encrypt/<key>`, payload đúng format |
| Database login từ credential thất bại | Engine DB role, lease TTL, connection pool | Kiểm tra quyền SQL, lease và chiến lược thay credential |
| Vault timeout/5xx | Mạng, cluster, auth engine, secrets engine | Timeout, backoff và retry hữu hạn theo loại thao tác |

**Không xem mọi HTTP 403 chỉ là thiếu policy:** token không hợp lệ/hết hạn và các vấn đề khác cũng có thể dẫn đến “permission denied”. Đầu tiên xác nhận client có token hợp lệ của đúng workload, sau đó kiểm tra path/capability/role. Tương tự, 404 có thể do mount hoặc tài nguyên thiếu; không thay thế secret bắt buộc bằng chuỗi trống để cho nghiệp vụ tiếp tục.

## 9. Kiểm tra quyền: thử được phép và bị từ chối

Một ma trận test nên được tạo trước khi viết logic xử lý secret:

| Workload | `secret/data/prod/orders/payment` (read) | `secret/data/prod/fraud/config` (read) | Transit encrypt `orders-pii` | Transit decrypt `orders-pii` |
|---|---|---|---|---|
| `orders-service` | **Cho phép** | Từ chối | **Cho phép** | Từ chối |
| `fraud-service` | Từ chối | Theo nghiệp vụ được cấp | Từ chối hoặc theo nhu cầu | **Cho phép** nếu nghiệp vụ yêu cầu |
| Workload không thuộc role | Từ chối | Từ chối | Từ chối | Từ chối |

Để kết luận role/policy có hiệu lực, cần chạy integration test với **Vault server thật trong môi trường test cô lập**, token và ServiceAccount/identity thử nghiệm, các mount/role/policy được tạo tường minh. Mock `VaultOperations` chỉ kiểm tra code Java phản ứng với kết quả; nó không xác thực Kubernetes auth, cấu trúc policy KV v2 hay quyền trên server.

Các bài kiểm tra nên gồm:

1. **Positive auth:** đúng ServiceAccount + namespace + audience login được và nhận token với policy dự kiến.
2. **Negative auth:** ServiceAccount hoặc namespace khác bị từ chối, token sai audience/issuer bị từ chối khi cấu hình yêu cầu.
3. **Positive authorization:** đúng role đọc được KV key orders và mã hóa bằng Transit.
4. **Negative authorization:** cùng token không đọc được key của service khác, không giải mã Transit, không ghi/xóa dữ liệu KV.
5. **Không lạm quyền list:** không liệt kê được metadata KV khi chưa có nhu cầu và policy `list`.
6. **Token lifecycle:** thử hết hạn/revoke; client quản lý login lại hoặc trả lỗi hữu hạn, không lộ token.
7. **Secret lifecycle:** với Database credential hoặc PKI, kiểm thử lease/certificate expiry và việc ứng dụng cập nhật tài nguyên runtime.
8. **Network failure:** Vault timeout, lỗi TLS, Vault 5xx; ứng dụng fail closed cho secret bắt buộc và không log payload.

### 9.1. Kiểm tra capability bằng công cụ quản trị

Khi có token test với quyền phù hợp, có thể dùng Vault CLI:

~~~bash
# Chạy trong môi trường test với token của đúng workload.
vault token capabilities secret/data/prod/orders/payment
vault token capabilities transit/encrypt/orders-pii
vault token capabilities transit/decrypt/orders-pii
~~~

Kết quả giúp quan sát quyền hiệu lực của token trên **API path** cụ thể, nhưng không thay thế thử request thật: auth method, mount/engine, key tồn tại và quyền/điều kiện ở hệ thống đích vẫn có thể gây lỗi.

## 10. Vận hành: bảo vệ thông tin xác thực và quan sát truy cập

Các nguyên tắc nên áp dụng cùng lúc:

- **Danh tính tách biệt:** mỗi service/job có workload identity và Vault role phù hợp; không dùng chung root token hoặc credential quản trị cho ứng dụng.
- **Quyền nhỏ và có phạm vi:** policy đúng path, capability và môi trường; hạn chế wildcard, `sudo` và quyền liệt kê không cần thiết.
- **TTL hợp lý:** Vault token ngắn hạn vừa đủ cho luồng nghiệp vụ, có chiến lược renewal/re-login; secret động/PKI có vòng đời riêng.
- **TLS có kiểm chứng:** Vault endpoint qua HTTPS, kiểm tra CA và hostname; không vô hiệu hóa certificate verification.
- **Không rò qua quan sát:** không log JWT, Vault token, `VaultResponse` chứa secret, private key hoặc plaintext; cẩn trọng với HTTP debug và management endpoints.
- **Audit và metrics:** bật audit devices phía Vault theo yêu cầu vận hành; theo dõi auth failures, 403 theo service/path đã làm sạch, latency, TTL/lease/certificate expiry và lỗi secrets engines.
- **Sự cố và rotation:** diễn tập revoke token, thay API key ở nhà phát hành, renew/reissue DB credential, thay TLS certificate và mất kết nối Vault.

### 10.1. Kịch bản “mất Vault” và yêu cầu fail closed

Nếu Vault tạm thời không sẵn sàng, một API key đã cache có thể vẫn hợp lệ nhưng khả năng dùng tiếp phải được quyết định theo policy nghiệp vụ và thời gian rotation. Nếu ứng dụng cần Transit để mã hóa trước khi lưu dữ liệu thì không được âm thầm bỏ qua bước mã hóa vì Vault timeout. Nếu credential Database đã hết lease, giữ lại giá trị cũ không làm account hợp lệ trở lại.

Retry phải có timeout, giới hạn số lần và backoff; các thao tác tạo credential hoặc ghi thay đổi có thể không idempotent nếu server đã xử lý nhưng response bị mất.

## 11. Tình huống thực hành: tìm lỗ hổng trong cấu hình

### Tình huống A — Role đúng, policy sai path

Workload `orders-service` login Kubernetes thành công. Policy được viết:

~~~hcl
# Sai nếu mount secret/ là KV v2 và cần đọc dữ liệu.
path "secret/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Nhưng lời gọi Java `opsForKeyValue("secret", KV_2).get("prod/orders/payment")` cần `read` trên `secret/data/prod/orders/payment`. Kết luận: role auth có thể đúng, song **ACL path không khớp request API**. Sửa policy cho đúng endpoint thay vì cấp quyền `secret/*`.

### Tình huống B — Một token dùng cho nhiều service

`orders-service` và `fraud-service` cùng dùng token từ một biến môi trường của hệ thống triển khai và token có quyền đọc tất cả secret production. Khi `orders-service` bị chiếm quyền, kẻ tấn công lấy được secret của `fraud-service`. Cách khắc phục là phân tách ServiceAccount/role/policies/TTL, giới hạn đường phát token và rà soát lại các bản sao secret đã bị đọc; không chỉ thay tên biến.

### Tình huống C — Token được gia hạn nhưng database không kết nối được

`LifecycleAwareSessionManager` gia hạn Vault token thành công, nhưng credential Database được cấp động đã đến hạn lease. Ứng dụng vẫn giữ HikariCP dùng credential cũ. Giải pháp thuộc vòng đời **secret động và connection pool**, không phải thêm vòng gia hạn Vault token.

### Tình huống D — Muốn “chỉ mã hóa, không giải mã”

`orders-service` chỉ cần ghi ciphertext. Policy chỉ có `update` cho `transit/encrypt/orders-pii` là điểm xuất phát phù hợp. `fraud-service` cần giải mã thì phải có identity/role/policy riêng cho `transit/decrypt/orders-pii`. Cả hai đều đi qua Vault auth nhưng quyền khác nhau.

## 12. Ghi nhớ và câu hỏi tự kiểm tra

Với Spring Vault, chuỗi quan hệ cốt lõi là:

~~~text
Danh tính workload
  -> Auth method + role
  -> Vault token (TTL, policies)
  -> VaultOperations / VaultTemplate
  -> API path + capability được kiểm tra ở Vault server
  -> Secrets engine
  -> Ứng dụng sử dụng kết quả và quản lý vòng đời
~~~

Muốn ứng dụng Java truy cập Vault an toàn, cả **xác thực workload**, **phân quyền trên đúng path** và **xử lý secret sau khi nhận** phải đúng. Spring Vault hỗ trợ giao tiếp/phiên, còn Vault server mới thực thi chính sách; hệ thống đích vẫn kiểm soát quyền sử dụng credential mà ứng dụng đã nhận.

Tự trả lời:

1. Vì sao Spring Security xác thực người dùng thành công không có nghĩa workload được đọc một KV key trong Vault?
2. Auth method, auth role, Vault token và ACL policy liên hệ với nhau như thế nào?
3. Với KV v2 mount `secret/` và key logic `prod/orders/payment`, policy path đọc dữ liệu là gì? Path liệt kê key có khác không?
4. Khi nào nên dùng Kubernetes auth, AppRole hoặc một phương thức danh tính cloud? Secret bootstrap của từng phương thức nằm ở đâu?
5. Token có quyền `read` trên KV có tự được phép gọi Transit encrypt không? Vì sao?
6. Revoke Vault token có tự làm API key tĩnh đã lộ ở bên thứ ba mất hiệu lực không?
7. Những negative test nào chứng minh `orders-service` không thể đọc bí mật hoặc giải mã dữ liệu của workload khác?

## Tài liệu chính thức

- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — VaultTemplate và VaultOperations](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html)
- [Spring Cloud Vault — Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
- [HashiCorp Vault — Authentication](https://developer.hashicorp.com/vault/docs/auth)
- [HashiCorp Vault — Kubernetes Auth Method](https://developer.hashicorp.com/vault/docs/auth/kubernetes)
- [HashiCorp Vault — AppRole Auth Method](https://developer.hashicorp.com/vault/docs/auth/approle)
- [HashiCorp Vault — Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2)
- [HashiCorp Vault — Tokens](https://developer.hashicorp.com/vault/docs/concepts/tokens)

> **Giới hạn ví dụ:** Tên mount, role, ServiceAccount, path và TTL là giả định phục vụ học tập. Cách cấu hình authentication/session và tham số role phụ thuộc phiên bản Spring Vault/Spring Cloud Vault/Vault cùng môi trường Kubernetes. Trước khi dùng trên hệ thống thật, cần đối chiếu đúng tài liệu phiên bản, kiểm tra quyền bằng token của workload và thử cả trường hợp bị từ chối.
