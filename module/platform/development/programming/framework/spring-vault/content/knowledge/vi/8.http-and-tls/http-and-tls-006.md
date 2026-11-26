# Phân biệt TLS của đường truyền với cert auth method

## 1. Hai lớp bảo mật thường bị nhầm trong Spring Vault

Ứng dụng Java dùng **Spring Vault** truy cập HashiCorp Vault qua HTTP API để đọc KV secrets, mã hóa bằng Transit, cấp chứng chỉ PKI và quản lý token, lease. Khi endpoint có dạng `https://vault.example.internal:8200`, kết nối đã dùng **TLS**. Tuy nhiên, TLS bảo vệ đường truyền và **Vault certificate authentication method** (`cert`) không phải là cùng một tính năng.

Có ba câu hỏi riêng:

1. **Kết nối có an toàn và đúng máy chủ không?** HTTPS/TLS cho phép Java kiểm tra chứng thư máy chủ, bảo vệ tính bí mật và toàn vẹn của lưu lượng.
2. **Có cần chứng minh danh tính client ở lớp TLS không?** Nếu listener hoặc gateway yêu cầu **mutual TLS (mTLS)**, Java phải xuất trình chứng thư client và chứng minh mình sở hữu private key.
3. **Vault cấp quyền dựa trên danh tính workload nào?** Vault authentication method (ví dụ Kubernetes, AppRole, token hoặc `cert`) xác định cách workload đăng nhập để nhận Vault token; token mang policy và vòng đời riêng.

Vì vậy **HTTPS không đồng nghĩa mTLS**, **mTLS không đồng nghĩa Vault cert auth**, và **Vault cert auth không thay thế được kết nối TLS an toàn**.

### Bảng đối chiếu nhanh

| Khái niệm | Cấp xử lý | Bằng chứng chính | Kết quả |
| --- | --- | --- | --- |
| HTTPS/TLS xác minh server | Giao thức truyền tải | Certificate chain + SAN hostname của Vault/ingress | Kênh được mã hóa và server được xác minh. |
| Mutual TLS (mTLS) | Giao thức truyền tải | Thêm client certificate và private key | Phía server/gateway xác minh client khi cấu hình yêu cầu. |
| Vault `cert` auth method | Vault authentication | Chứng thư client được Vault nhận và khớp cấu hình cert auth | Nếu login hợp lệ, **Vault token** được cấp. |
| Vault policy | Vault authorization | Policy gắn với token | Quy định API path và thao tác được phép. |
| Token/lease TTL | Vòng đời credential | Thời hạn và quy tắc renew/revoke | Kiểm soát hiệu lực của token hoặc secret động, độc lập với thời hạn chứng thư TLS. |

Ví dụ: một `VaultTemplate` có thể gọi Vault qua HTTPS xác minh server, đăng nhập bằng **Kubernetes authentication** và đọc KV secrets thành công **mà không dùng client certificate hoặc cert auth method**.

## 2. Luồng TLS: xác minh máy chủ trước khi gửi API

Trong HTTPS thông thường, Vault listener hoặc reverse proxy xuất trình **server certificate**. Java dùng truststore chứa CA phù hợp để dựng chuỗi chứng thư và xác minh tên host với Subject Alternative Name (SAN).

```text
 Java / HTTP client                      Vault hoặc HTTPS gateway
       │                                           │
       ├──────── TLS ClientHello ─────────────────►│
       │◄─────── Server certificate ───────────────┤
       │  Kiểm tra CA, hiệu lực, SAN/hostname      │
       ├════════ Kênh TLS được bảo vệ ═════════════┤
       ├──────── POST /v1/auth/... ───────────────►│
       │◄─────── Vault token (nếu login đúng) ─────┤
       ├──────── GET /v1/secret/... ──────────────►│
```

Điểm quan trọng:

- `truststore` của Java chứa chứng thư CA được **tin để xác minh máy chủ**. Truststore thông thường không chứa private key của ứng dụng.
- Host trong URI, ví dụ `vault.example.internal`, phải khớp SAN trên **server certificate** của điểm kết thúc TLS. Đúng CA nhưng sai hostname vẫn phải bị từ chối.
- TLS không tự quyết định Vault sẽ chấp nhận AppRole, Kubernetes JWT, token hay client certificate làm phương thức đăng nhập.
- Mã HTTP `403` sau khi TLS hoàn tất thường là dấu hiệu cần kiểm tra token/policy/namespace hoặc quy tắc auth, không phải bằng chứng rằng TLS bị lỗi.

Nếu gọi qua ingress kết thúc TLS, Java phải tin **chứng thư của ingress**. Mức bảo vệ của kết nối ingress đến Vault backend là cấu hình của chặng riêng, không suy ra chỉ từ HTTPS ở phía client.

## 3. Mutual TLS: thêm danh tính của client ở lớp truyền tải

Với **mTLS**, máy chủ yêu cầu chứng thư client trong TLS handshake. Java dùng **keystore** có client certificate và private key để chứng minh danh tính; server hoặc gateway dùng CA/trust configuration phía mình để kiểm tra chứng thư đó.

```text
 Java                                Vault TLS listener
 ┌──────────────────────────┐        ┌──────────────────────────┐
 │ Truststore: CA của server│        │ Server certificate + key │
 │ Keystore: client cert+key│        │ Trusted client CA        │
 └──────────────────────────┘        └──────────────────────────┘
             │                                  │
             │◄────── Server certificate ───────│
             │      Java xác minh server       │
             │◄────── CertificateRequest ──────│
             │─────── Client certificate ──────►│
             │   chứng minh sở hữu private key  │
             │         Server xác minh client  │
             │◄══════ TLS handshake OK ════════│
             │─────── HTTP Vault API ──────────►│
```

Sơ đồ chỉ mô tả các bước logic; thông điệp thực tế thay đổi giữa TLS 1.2 và 1.3. **Private key không được gửi** trong handshake. Nếu mTLS bắt buộc nhưng Java thiếu chứng thư hợp lệ, kết nối có thể bị từ chối **trước khi Vault HTTP API nhận request**.

### Phân biệt keystore và truststore

| Phía Java cần | Tệp thường gặp | Nội dung | Dùng cho |
| --- | --- | --- | --- |
| Truststore | `vault-truststore.p12` | Chứng thư CA tin cậy, không cần client private key | Xác minh **server**. |
| Client keystore | `vault-client.p12` | `PrivateKeyEntry`: private key, client certificate và chain | Xuất trình danh tính **client** khi peer yêu cầu. |

Phía **Vault listener hoặc gateway** cũng cần nguồn tin cậy để kiểm tra client certificate. Đó là trust configuration **của server**, không phải truststore của JVM.

Chứng thư client cần đúng thời hạn, issuer/chain, EKU cho `clientAuth` khi EKU được áp dụng, thuật toán khóa phù hợp và danh tính được phép. **Đã nhập CA vào truststore Java chưa đủ để bật mTLS**: Java còn cần client certificate cùng private key tương ứng.

## 4. Vault cert auth: đăng nhập để nhận token

Vault cung cấp authentication method tên **`cert`**. Method này sử dụng chứng thư client được trình qua kết nối TLS và so khớp với các cấu hình chứng thư/CA, ràng buộc danh tính do quản trị viên thiết lập tại mount auth.

Khi login hợp lệ, Vault trả về **client token** cùng metadata/thời hạn tương ứng. Các request về sau sử dụng token để được Vault áp dụng policy:

```text
1. Java kết nối HTTPS và trình client certificate khi TLS yêu cầu
                        │
                        ▼
2. POST /v1/auth/cert/login
                        │
                        ▼
3. Vault cert auth kiểm tra chứng thư và cấu hình danh tính
                        │
            hợp lệ? ────┴──── không → login thất bại
               │
              có
               ▼
4. Vault cấp token với policy và TTL được cấu hình
                        │
                        ▼
5. VaultTemplate dùng token gọi KV / Transit / PKI...
```

**Chỉ hoàn tất TLS handshake không đồng nghĩa đã thực hiện bước 2–4.** Một ứng dụng có thể dùng client certificate để qua gateway nhưng vẫn nhận `403` từ Vault vì chưa có token hoặc policy không đủ.

Ngược lại, nếu triển khai chọn `authentication: CERT` nhưng Java không thể gửi client certificate hợp lệ tới nơi Vault lấy thông tin xác thực, Vault không thể dựa vào đúng danh tính chứng thư để đăng nhập.

### Mount path của cert auth khác đường dẫn TLS

Ví dụ khi bật method ở đường dẫn mặc định:

```text
Vault endpoint:          https://vault.example.internal:8200
Certificate auth login:  POST /v1/auth/cert/login
KV v2 read:              GET  /v1/secret/data/payments/config
```

`/auth/cert/login` là **đường dẫn HTTP API của auth method**; nó không phải đường dẫn tệp chứng thư, không phải `keystore` và không được nối vào URI cơ sở của `VaultEndpoint`. Nếu method được mount ở path khác, tuyến login cũng thay đổi tương ứng.

## 5. Ba mô hình kiến trúc thực tế

### Mô hình A — HTTPS, không yêu cầu client certificate, dùng Kubernetes/AppRole

```text
Java ── TLS: xác minh Vault ──► Vault
Java ── Kubernetes/AppRole login ──► Vault token
Java ── VaultTemplate + token ──► KV / Transit / PKI
```

Đây là lựa chọn phổ biến khi danh tính workload đã được cung cấp bởi nền tảng triển khai. Ứng dụng cần **trust server CA** và đúng hostname; chỉ cần client keystore nếu listener hoặc mạng yêu cầu mTLS.

### Mô hình B — mTLS bắt buộc, Vault auth vẫn dùng Kubernetes/AppRole

```text
Java ── client certificate + mTLS ──► Vault listener/gateway
Java ── Kubernetes/AppRole login ──► Vault token
Java ── VaultTemplate + token ──► KV / Transit / PKI
```

Trong mô hình này, client certificate bảo vệ/kiểm soát **đường vào HTTPS**. Workload đăng nhập Vault bằng phương thức **khác cert**. Vì thế bật mTLS không có nghĩa phải chọn `CERT` trong Spring Cloud Vault.

### Mô hình C — mTLS và Vault cert auth

```text
Java ── client certificate + TLS ──► Vault listener
Java ── POST /v1/auth/cert/login ──► Vault cert auth
Java ◄──── Vault token + policy ─── Vault
Java ── VaultTemplate + token ──► KV / Transit / PKI
```

Mô hình này dùng chứng thư client làm cơ sở xác thực workload **tại Vault**. Ngoài cấu hình TLS, quản trị viên phải bật `cert` auth method, đăng ký/ràng buộc chứng thư hoặc CA với danh tính và policy phù hợp. Nếu không có cấu hình auth, việc TLS đã xác minh client cũng **không thể tự sinh token**.

| Câu hỏi | Mô hình A | Mô hình B | Mô hình C |
| --- | --- | --- | --- |
| Java xác minh server TLS? | Có | Có | Có |
| Java cần client certificate? | Không, nếu endpoint không yêu cầu | Có | Có |
| Vault auth method | Kubernetes/AppRole hoặc method khác | Kubernetes/AppRole hoặc method khác | `cert` |
| Vault cấp token sau login? | Có | Có | Có |
| Policy vẫn bắt buộc? | Có | Có | Có |

## 6. Cấu hình phía Vault: listener TLS và cert auth là hai việc

### 6.1. Cấu hình transport TLS của Vault

Ví dụ **minh họa cấu hình listener khi muốn bắt buộc mTLS**:

```hcl
listener "tcp" {
  address                            = "0.0.0.0:8200"
  tls_cert_file                      = "/etc/vault/tls/vault-server-fullchain.pem"
  tls_key_file                       = "/etc/vault/tls/vault-server.key"
  tls_client_ca_file                 = "/etc/vault/tls/trusted-client-ca.pem"
  tls_require_and_verify_client_cert = "true"
}
```

Các trường được dùng với vai trò:

- `tls_cert_file`, `tls_key_file`: chứng thư và private key **của server**.
- `tls_client_ca_file`: CA được listener dùng để kiểm tra chứng thư **client**.
- `tls_require_and_verify_client_cert`: yêu cầu client có chứng thư hợp lệ khi listener cấu hình mTLS bắt buộc.

Khi bật yêu cầu mTLS cho listener, **mọi client đi qua listener đó** (ví dụ CLI, health probe, agent, ứng dụng khác) có thể phải có chứng thư phù hợp. Chỉ bật theo yêu cầu kiến trúc và kiểm thử toàn bộ client trước khi triển khai.

**Đừng nhầm:** bật `tls_require_and_verify_client_cert` là chính sách của **TLS listener**, không phải lệnh bật auth method `cert`. Cách Vault yêu cầu chứng thư client khi không bắt buộc mTLS và các tùy chọn listener khác phụ thuộc cấu hình/phiên bản Vault; khi triển khai cert auth, phải xác minh client certificate thật sự có mặt ở kết nối mà Vault xử lý.

### 6.2. Bật auth method và cấu hình danh tính

Một ví dụ lệnh **phía quản trị Vault** (giả sử policy `payments-read` đã được tạo với quyền tối thiểu và `payments-client.crt` được kiểm tra nguồn gốc):

```bash
vault auth enable cert

vault write auth/cert/certs/payments-worker \
  display_name="payments-worker" \
  policies="payments-read" \
  certificate=@payments-client.crt
```

Lệnh thứ nhất bật auth method tại mount `cert/` mặc định. Lệnh thứ hai đăng ký một chứng thư được phép dùng cho auth method đó và policy áp dụng khi login thành công. Vault có thể hỗ trợ ràng buộc theo CA hoặc các thuộc tính chứng thư, nhưng phải xác nhận những giới hạn nhận diện, quyền và tùy chọn cụ thể theo **phiên bản Vault** đang chạy. Không cấp chung policy quyền rộng cho mọi chứng thư được một CA cấp.

Ví dụ minh họa phía client bằng Vault CLI:

```bash
export VAULT_ADDR="https://vault.example.internal:8200"
export VAULT_CACERT="/etc/vault/tls/vault-server-ca.pem"

vault login -method=cert \
  -client-cert="/etc/vault/tls/payments-client.crt" \
  -client-key="/etc/vault/tls/payments-client.key" \
  name="payments-worker"
```

`VAULT_CACERT` chỉ ảnh hưởng cách **Vault CLI xác minh server**; nó không tự trở thành truststore cho HTTP client Java. Nếu quản trị viên dùng path cert auth khác mặc định, cần cập nhật mount/login path thích hợp.

**Không dùng private key thật trong tài liệu, repository hay log.** Các tệp chứng thư/khóa trong ví dụ là đường dẫn giả định được cấp cho workload; không được tự tạo danh tính giả rồi coi là đã được Vault cấp quyền.

## 7. Spring Vault và Spring Cloud Vault: chọn đúng chỗ cấu hình

### 7.1. Chỉ cần TLS server-authentication

Với Spring Cloud Vault, một cấu hình minh họa kết nối TLS và xác thực bằng token có sẵn:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      authentication: TOKEN
      token: "${VAULT_TOKEN}"
      ssl:
        trust-store: "file:/etc/vault/tls/vault-truststore.p12"
        trust-store-password: "${VAULT_TRUSTSTORE_PASSWORD}"
```

Trong ví dụ này chỉ có **truststore của server**; không có client keystore vì listener không yêu cầu client certificate. `TOKEN` chỉ là ví dụ để tách vai trò: trong vận hành thực tế, nên lựa chọn phương thức đăng nhập theo workload và quản lý vòng đời token phù hợp.

### 7.2. mTLS ở transport, Vault auth bằng phương thức khác

Với mô hình B, keystore giúp hoàn tất TLS, còn `authentication` vẫn chọn phương thức đăng nhập riêng. Ví dụ minh họa:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      authentication: KUBERNETES
      ssl:
        key-store: "file:/etc/vault/tls/vault-client.p12"
        key-store-password: "${VAULT_CLIENT_KEYSTORE_PASSWORD}"
        trust-store: "file:/etc/vault/tls/vault-truststore.p12"
        trust-store-password: "${VAULT_TRUSTSTORE_PASSWORD}"
```

Đây là cấu hình **rút gọn cho mục đích phân biệt**; dự án thực tế còn phải khai báo role/path/token service account của Kubernetes authentication theo phiên bản Spring Cloud Vault và cấu hình Vault auth mount. Keystore cho mTLS không thay các thuộc tính đăng nhập đó.

### 7.3. Vault cert auth method

Với mô hình C, khi Vault cert auth đã được bật, cấu hình Spring Cloud Vault minh họa:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      authentication: CERT
      ssl:
        key-store: "file:/etc/vault/tls/vault-client.p12"
        key-store-password: "${VAULT_CLIENT_KEYSTORE_PASSWORD}"
        trust-store: "file:/etc/vault/tls/vault-truststore.p12"
        trust-store-password: "${VAULT_TRUSTSTORE_PASSWORD}"
```

`authentication: CERT` yêu cầu tích hợp đăng nhập Vault qua certificate auth method. Dòng `ssl.key-store` cung cấp client key material để TLS có thể trình chứng thư khi server yêu cầu. **Phải có cả** cấu hình TLS/keystore phù hợp **và** cấu hình auth method phù hợp phía Vault; không đặt `authentication: CERT` rồi kỳ vọng certificate tự xuất hiện.

Các thuộc tính `spring.cloud.vault.*` chỉ có hiệu lực khi dự án tích hợp **Spring Cloud Vault** tương ứng. Khi dùng **Spring Vault trực tiếp**, người viết ứng dụng có thể tạo `VaultEndpoint`, `VaultTemplate`, `ClientAuthentication` và HTTP transport riêng; cấu hình `SSLContext` của client cần được cấp **client keystore** cùng **truststore**. Sau đó chọn authentication implementation tương ứng với phương thức muốn dùng. Đừng mặc định mọi `VaultTemplate` tùy chỉnh sẽ đọc cấu hình `spring.cloud.vault.ssl` từ YAML.

Lưu ý nữa: `spring.config.import: "vault://"` (nếu dùng Config Data integration) là cú pháp import cấu hình từ Vault, **không phải protocol TLS**, cert auth method hay đường dẫn login.

## 8. Tại sao gateway có thể làm Vault cert auth thất bại?

Giả sử kiến trúc:

```text
Java ── mTLS ──► Ingress (TLS termination) ── HTTPS/HTTP ──► Vault
                    │
                    └── thấy client certificate của Java
                                                   │
                                              Vault có thể
                                              không thấy
                                              chứng thư gốc
```

Nếu ingress **kết thúc TLS**, TLS connection từ Java đến ingress chấm dứt tại đó. Vault ở phía sau thường chỉ thấy kết nối mới từ ingress, **không mặc nhiên nhận được TLS peer certificate của Java**.

Hệ quả:

- **Mô hình B** vẫn khả thi: ingress xác minh mTLS, sau đó workload dùng Kubernetes/AppRole/token để đăng nhập Vault.
- Với **mô hình C**, phải bảo đảm Vault cert auth thực sự nhận được danh tính client certificate theo **kiến trúc/tích hợp mà Vault hỗ trợ**. Một lựa chọn là **TLS passthrough** để Vault kết thúc TLS trực tiếp; các cấu hình khác cần kiểm chứng kỹ cơ chế chuyển tiếp và trust boundary.
- Đừng tùy tiện gửi certificate trong một HTTP header có thể bị client giả mạo và giả định Vault sẽ coi đó là TLS client identity.

Trong cả hai mô hình, endpoint Java gọi phải có certificate server hợp lệ với đúng CA và SAN/hostname. Nếu ingress kết thúc HTTPS, chính ingress là bên Java xác minh; ingress có trách nhiệm bảo vệ kết nối tới Vault theo chính sách hệ thống.

## 9. AuthN, AuthZ và vòng đời chứng thư/token khác nhau

Giả sử client certificate sẽ hết hạn sau 24 giờ, còn Vault login bằng `cert` cấp token TTL 1 giờ:

- **Chứng thư client** quyết định khả năng tạo TLS handshake mới hoặc login mới dựa trên cert vào thời điểm kiểm tra. Gia hạn Vault token không làm chứng thư kéo dài hiệu lực.
- **Vault token** có TTL, renewal và khả năng revoke theo chính sách Vault. Thay hoặc thu hồi chứng thư client **không mặc nhiên** thu hồi mọi token đã phát hành trước đó.
- **Vault policy** tiếp tục quyết định quyền đọc KV, sử dụng Transit, phát hành PKI hay quản lý secret động. Chứng thư ký bởi CA được tin cậy không tự cấp quyền root.
- **Lease** của dynamic secrets là vòng đời khác; không dùng hạn chứng thư TLS thay cho lease duration hoặc thời điểm renew/revoke.

Khi xoay client certificate, nhiều HTTP client Java giữ `SSLContext` và kết nối TLS đã mở trong bộ nhớ; thay `.p12` trên disk **chưa chắc** khiến lần gọi tiếp theo sử dụng chứng thư mới. Cần kiểm thử khả năng nạp lại cấu hình, tạo lại connection/HTTP client hoặc rollout ứng dụng theo quy trình có kiểm soát.

Nếu dùng `cert` auth, việc đổi certificate/CA có thể đòi hỏi điều chỉnh cấu hình cert auth phía Vault **và** trusted client CA của listener/gateway (nếu có), đồng bộ trước khi chứng thư cũ hết hạn. Theo dõi đồng thời cả lỗi TLS và lỗi login/token renewal.

## 10. Chẩn đoán: lỗi ở TLS hay lỗi cert auth?

| Triệu chứng | Lớp cần xem | Kiểm tra |
| --- | --- | --- |
| `PKIX path building failed` | Java xác minh server TLS | Truststore Java, issuer/chain server và CA của endpoint HTTPS thật. |
| `No subject alternative DNS name matching` | Java xác minh hostname | Tên trong URI và SAN của server/ingress certificate. |
| TLS alert `certificate_required` hoặc `bad_certificate` | mTLS handshake | Client keystore, private key entry, client EKU, chain và client CA được server tin. |
| Không thấy client certificate ở Vault | TLS termination/đường đi | Có gateway kết thúc TLS trước Vault không, Vault có nhận TLS peer certificate đúng cách không? |
| HTTP lỗi tại `/v1/auth/cert/login` | Vault cert authentication | Auth method đã bật chưa, mount path và chứng thư/các ràng buộc identity có khớp không? |
| Login thành công nhưng KV trả HTTP `403` | Vault authorization | Token, policy trên KV path (KV v1/v2), namespace và hiệu lực token. |
| Chứng thư hợp lệ nhưng token hết hạn | Token/session lifecycle | Theo dõi token TTL, renewal, re-login; TLS cert validity là thời hạn khác. |
| CLI cert login được, Java không | Khác cấu hình TLS/client auth | So sánh `VAULT_CACERT`, `-client-cert`, `-client-key` của CLI với keystore/truststore và auth implementation của Java. |

Khi debug, có thể dùng công cụ độc lập để kiểm tra **lớp truyền tải**:

```bash
curl --verbose \
  --cacert vault-server-ca.pem \
  --cert payments-client.crt \
  --key payments-client.key \
  "https://vault.example.internal:8200/v1/sys/health"
```

`--cacert` kiểm tra server; `--cert` và `--key` cung cấp client certificate cho mTLS nếu peer yêu cầu. Endpoint `sys/health` không phải chứng minh cert auth đã login; nó có thể trả các mã trạng thái khác nhau khi Vault standby, sealed hoặc uninitialized.

Để kiểm tra **Vault cert auth**, phải thử đúng API login/mount (ví dụ qua `vault login -method=cert`) và xác minh token/policy được cấp. `curl` thành công **không** đồng nghĩa cấu hình `VaultTemplate` trong JVM đã đọc keystore/truststore đúng. Khi cần, bật TLS handshake debug của Java trong môi trường kiểm soát:

```text
-Djavax.net.debug=ssl,handshake,keymanager,trustmanager
```

Không dùng `curl -k`, Java trust-all `TrustManager`, `HostnameVerifier` chấp nhận mọi host hoặc `VAULT_SKIP_VERIFY` làm giải pháp. Các cách đó bỏ xác minh danh tính endpoint và có thể làm lộ Vault token, secret hoặc private key qua kênh giả mạo. Khi ghi log, giữ nguyên nhân gốc nhưng **không ghi token, password, private key, certificate key material hoặc request body nhạy cảm**.

## 11. Kiểm thử tích hợp theo từng lớp

Thực hiện kiểm thử bằng **đúng HTTP client và authentication setup của ứng dụng Spring Vault**, vì CLI và Java có thể dùng CA/client key store khác nhau:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| HTTPS với CA đúng, SAN đúng, không yêu cầu mTLS | TLS thành công; Vault auth method được chọn có thể login. |
| HTTPS với CA chưa được tin hoặc SAN sai | Kết nối TLS thất bại trước khi request mang token tới API. |
| Listener yêu cầu mTLS nhưng Java không có client keystore | Handshake bị từ chối. |
| Listener chấp nhận mTLS, ứng dụng dùng Kubernetes/AppRole | Vault login theo Kubernetes/AppRole hoạt động, không cần chọn `CERT`. |
| Listener chấp nhận mTLS nhưng cert auth chưa được bật | TLS vẫn có thể thành công, còn `/auth/cert/login` thất bại. |
| Cert auth được bật, certificate không khớp ràng buộc | Vault không cấp token cho danh tính client đó. |
| Cert auth login đúng, policy thiếu quyền KV/Transit/PKI | Token được cấp nhưng request ngoài quyền bị Vault từ chối. |
| Gateway kết thúc mTLS mà Vault không thấy client cert | Cert auth không thể dựa vào certificate gốc nếu không có cơ chế được hỗ trợ. |
| Xoay client cert/CA | Handshake mới, cert login, token renewal và KV/Transit/PKI tiếp tục theo thiết kế sau rollout. |

Đừng dừng ở bài test "HTTP 200 từ `sys/health`": trường hợp đó chỉ chứng minh đường đi HTTPS đến endpoint ở mức tương ứng, chưa kiểm tra Vault login và Vault policy.

## 12. Tình huống tự luyện

**Tình huống A — HTTPS đã chạy ổn, có cần `authentication: CERT` không?** Không. Nếu workload đã đăng nhập bằng Kubernetes auth hoặc AppRole và listener không yêu cầu cert auth, TLS xác minh server vẫn hoàn toàn hợp lệ mà không cần `CERT`.

**Tình huống B — Bắt buộc mTLS nhưng đã có AppRole:** Java phải có keystore client để đi qua listener/gateway. Sau handshake, AppRole vẫn đăng nhập và nhận Vault token; không cần đổi sang cert auth chỉ vì mTLS được bật.

**Tình huống C — Bật cert auth ở Vault nhưng chỉ cấu hình truststore Java:** Java mới có CA để tin server, chưa có client private key/chứng thư. Nếu TLS connection không cung cấp client certificate thì Vault không có danh tính chứng thư cần thiết để cert login.

**Tình huống D — Gateway đã xác minh client, Vault cert login vẫn thất bại:** Nếu gateway kết thúc mTLS, Vault backend có thể không thấy chứng thư của Java. Xác định trust boundary và chọn TLS passthrough hoặc cách tích hợp được Vault hỗ trợ; không giả định HTTP header tùy ý sẽ thay thế TLS peer identity.

**Tình huống E — Cert login thành công nhưng `VaultTemplate` bị từ chối đọc secret:** Kiểm tra token, policy, path KV v2 và namespace. Xác minh TLS và cert auth chỉ là điều kiện để lấy token; quyền từng thao tác do policy quyết định.

### Ghi nhớ

**TLS** bảo vệ đường truyền và xác minh server. **mTLS** bổ sung việc phía server xác minh client certificate tại lớp truyền tải. **Vault cert auth** là phương thức đăng nhập dùng danh tính certificate để **xin Vault token**; sau đó token và policy mới quyết định quyền dùng KV, Transit, PKI hay token/lease APIs. Khi cấu hình Spring Vault, hãy xác định **ai kết thúc TLS**, **Java có cần keystore hay chỉ truststore**, **Vault auth method nào đang dùng** và **policy nào được cấp**. Đó là bốn câu hỏi khác nhau cần kiểm thử riêng.
