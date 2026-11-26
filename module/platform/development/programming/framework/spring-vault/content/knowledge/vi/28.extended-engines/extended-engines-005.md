# SSH signing và yêu cầu theo hợp đồng endpoint

Trong chương **Engine mở rộng**, HashiCorp Vault không chỉ lưu secret KV, cấp chứng thư PKI hay thực hiện Transit encryption. **SSH secrets engine** có thể đóng vai trò *SSH Certificate Authority (SSH CA)*: nhận khóa công khai của một người dùng hoặc máy chủ, kiểm tra các giới hạn của role và phát hành **chứng thư SSH ngắn hạn** để OpenSSH xác thực.

Khi lập trình Java với **Spring Vault**, điểm quan trọng là phải hiểu **hợp đồng của endpoint**: đường dẫn, HTTP method, trường bắt buộc, quyền token, giới hạn của role, dạng response và lỗi dự kiến. Một lời gọi `VaultTemplate.write(...)` trả kết quả thành công **chưa chứng minh** máy chủ SSH sẽ cho phép đăng nhập; phía OpenSSH còn kiểm tra CA đáng tin cậy, principal, hiệu lực chứng thư và các chính sách cục bộ.

Bài này sử dụng ví dụ dịch vụ tự động triển khai có danh tính workload, được cấp phép yêu cầu Vault ký khóa công khai cho tài khoản `deploy` trên máy chủ nội bộ. Các thao tác tạo SSH CA và role thuộc trách nhiệm quản trị; ứng dụng Spring chỉ thực hiện yêu cầu ký theo hợp đồng đã công bố.

## 1. SSH certificate signing giải quyết vấn đề gì?

Trong cách cấu hình truyền thống, mỗi máy chủ SSH giữ danh sách khóa công khai của người được phép đăng nhập trong `authorized_keys`. Khi số máy chủ, kỹ sư và workload tăng, việc phát tán, xóa và đổi từng khóa trở nên phức tạp.

Với mô hình SSH CA:

1. Người dùng hoặc workload tạo cặp khóa SSH và **giữ private key ở phía mình**.
2. Vault SSH engine ký **public key** theo role và tạo SSH *user certificate* có hiệu lực ngắn.
3. Máy chủ `sshd` đã được cấu hình tin **public key của SSH CA** do Vault quản lý.
4. Người dùng trình cả private key (để chứng minh sở hữu khóa) và chứng thư SSH tương ứng; `sshd` kiểm tra chữ ký CA, principal, hiệu lực và các hạn chế khác.

~~~mermaid
sequenceDiagram
    participant W as Java workload
    participant V as Vault SSH signer
    participant S as sshd
    W->>W: Giữ private key, lấy public key
    W->>V: POST /ssh-client-signer/sign/deploy-user
    Note over W,V: Xác thực workload và kiểm tra Vault policy/role
    V-->>W: data.signed_key, data.serial_number
    W->>W: Lưu chứng thư SSH ngắn hạn
    W->>S: SSH handshake: public cert + proof of private key
    S->>S: Verify trusted CA, principal, time, options
    S-->>W: Chấp nhận hoặc từ chối đăng nhập
~~~

SSH CA **không phải** CA X.509 của PKI engine. Chứng thư `ssh-ed25519-cert-v01@openssh.com` hoặc `ssh-rsa-cert-v01@openssh.com` là định dạng chứng thư SSH của OpenSSH; chúng **không phải** PEM certificate dùng cho HTTPS/mTLS. Tương tự, SSH signing cũng **khác** thao tác Transit sign dùng chữ ký cho dữ liệu ứng dụng.

| Cơ chế | Dữ liệu và endpoint | Mục đích |
| --- | --- | --- |
| **SSH signer** | Khóa công khai SSH → `ssh-client-signer/sign/<role>` | Cấp chứng thư SSH để xác thực user/host trong OpenSSH |
| **Vault PKI** | CSR hoặc yêu cầu cấp khóa → `pki/sign/<role>`, `pki/issue/<role>` | Cấp X.509 cho TLS/mTLS |
| **Vault Transit** | Dữ liệu byte hoặc digest → `transit/sign/<key>` | Ký dữ liệu ứng dụng; kết quả không tự trở thành SSH certificate |
| **SSH OTP** | SSH engine `creds/<role>` và `verify` | Cơ chế SSH one-time password, khác quy trình CA signing |

Tài liệu này tập trung vào **SSH CA signing**. Các phương án SSH OTP có thiết lập máy chủ và hợp đồng API khác.

## 2. Trách nhiệm giữa Vault, workload và OpenSSH

| Thành phần | Sở hữu | Phải kiểm tra |
| --- | --- | --- |
| Quản trị Vault | Mount SSH engine, SSH CA signing key, role và policy | CA key được bảo vệ; role chỉ ký cho danh tính được cấp |
| Workload Java | Public key, request ký, token Vault từ workload authentication | Đúng mount/role, TTL, principal, dữ liệu response |
| Chủ sở hữu private key | Khóa SSH bí mật nằm trên thiết bị, agent hoặc secret store phù hợp | Private key không xuất hiện trong request `sign`, logs hay source |
| Máy chủ SSH | `TrustedUserCAKeys`, account và quy tắc `sshd` | CA signature, thời hạn, principal, revocation policy và local authorization |
| Hệ thống vận hành | Lịch cấp chứng thư mới, kiểm thử đăng nhập, cảnh báo | Chứng thư không hết hạn trước khi job hoàn tất; lỗi xác thực được phân loại |

Hệ thống giữ CA public key trên máy chủ SSH để xác minh chữ ký. Bất kỳ ai có public key CA **không thể** tự ký chứng thư; SSH CA private key cần được bảo vệ trong Vault hoặc hệ thống khóa được Vault quản lý.

### User certificate và host certificate

- **User certificate** (`cert_type=user`): chứng minh người/workload đăng nhập đã được CA ký; máy chủ thường dùng `TrustedUserCAKeys` để tin CA. `valid_principals` là tên tài khoản hoặc danh tính mà cert cho phép.
- **Host certificate** (`cert_type=host`): chứng minh danh tính máy chủ SSH; phía client dùng `@cert-authority` trong `known_hosts` để tin CA host. Vai trò này cần role cho phép host certificates và giới hạn hostname.

Nên sử dụng **CA/role tách biệt cho user signing và host signing** để giảm ảnh hưởng nếu một loại quyền bị cấu hình sai.

## 3. Hợp đồng API của endpoint SSH sign

Ví dụ: SSH engine được mount ở `ssh-client-signer/`; role `deploy-user`; tài khoản SSH mục tiêu `deploy`. Dù tên mount có chữ “client”, Vault vẫn gọi đường dẫn theo tên mount thực tế, không tự thêm tiền tố `ssh/`.

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| HTTP method | `POST` | Gửi yêu cầu cấp chứng thư; thao tác tạo ra kết quả mới |
| Vault API path | `/v1/ssh-client-signer/sign/deploy-user` | `sign` + tên role, không phải tên khóa public |
| Spring Vault path | `ssh-client-signer/sign/deploy-user` | Đường dẫn tương đối cho `VaultOperations.write`; không thêm `/v1/` |
| Authentication | Vault token hợp lệ | Được tạo từ workload auth và có policy phù hợp |
| Request Content-Type | `application/json` | Body dùng JSON, `public_key` là một chuỗi OpenSSH |
| Response | `data.signed_key`, `data.serial_number` | Chứng thư SSH đã ký và serial để theo dõi/audit |

### Các tham số request

| Trường | Bắt buộc? | Ví dụ | Vai trò / điều kiện |
| --- | --- | --- | --- |
| `public_key` | **Có** | `ssh-ed25519 AAAAC3... deploy-lab` | Public key OpenSSH cần ký; không gửi private key |
| `valid_principals` | Có nếu role không định nghĩa default principal phù hợp | `deploy` | Danh tính SSH mà chứng thư cho phép; bị ràng buộc bởi role |
| `ttl` | Không | `15m` | Thời hạn mong muốn, không vượt giới hạn role/mount |
| `cert_type` | Không | `user` hoặc `host` | Mặc định `user`; role phải cho phép loại yêu cầu |
| `key_id` | Không | `deploy-job-20261125` | Dùng để định danh/audit; role có thể không cho caller tự đặt |
| `extensions` | Không | `{"permit-pty": ""}` | Chức năng được phép của SSH cert; role kiểm soát |
| `critical_options` | Không | tùy cấu hình | Giới hạn bắt buộc mà SSH client/server hỗ trợ và tuân theo |

Một request tối thiểu có thể là:

~~~json
{
  "public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA... deploy-lab",
  "valid_principals": "deploy",
  "cert_type": "user",
  "ttl": "15m"
}
~~~

Đây chỉ là ví dụ minh họa định dạng public key; chuỗi có dấu `...` **không phải khóa hợp lệ để gọi thật**. Client cần truyền nguyên một public key thực được lấy từ khóa trong workload.

Response thành công điển hình:

~~~json
{
  "data": {
    "serial_number": "9e00cabc0b4a1a12",
    "signed_key": "ssh-ed25519-cert-v01@openssh.com AAAA... deploy-lab"
  },
  "renewable": false
}
~~~

Các trường bổ sung như `request_id`, `lease_id`, `lease_duration` và metadata khác phụ thuộc phiên bản/đường đi; **không nên buộc logic ứng dụng vào response giả lập ở trên**. Phần quan trọng là kiểm tra `data.signed_key` không rỗng và xác nhận nội dung SSH certificate được OpenSSH chấp nhận. Vault ký và trả chứng thư nhưng **không giữ hộ bản cert đã cấp để có thể lấy lại theo serial**; cần lưu/triển khai response khi còn cần dùng.

**Các ràng buộc cần đối chiếu trước khi gửi request:**

1. **Role** `deploy-user` tồn tại dưới đúng mount, có `key_type=ca` và `allow_user_certificates=true`.
2. **Principal** mong muốn được role cho phép, ví dụ `allowed_users=deploy`; mặc định của role cũng có thể cấp principal mà không cần tham số từ request.
3. **TTL** không vượt `max_ttl`; không nhận cert có hiệu lực quá ngắn so với công việc triển khai.
4. **Khóa công khai** thuộc loại/độ dài mà Vault cho phép; người gửi phải sở hữu private key khớp.
5. **SSH server** đã tin đúng SSH CA và có account/authorized principals theo thiết kế.
6. **Policy Vault** cho phép endpoint ký; quyền gọi `/config/ca` hoặc `/roles` không được suy ra từ quyền ký.

Không lấy các giá trị `valid_principals`, `cert_type`, `extensions`, `critical_options` trực tiếp từ tham số người dùng rồi chuyển nguyên vào API ký. Workload phải liên kết danh tính đã xác thực với role/giới hạn đã được duyệt.

## 4. Thiết lập SSH CA và role cho môi trường thực hành

Các lệnh bên dưới chạy bởi người quản trị Vault; đây **không phải** công việc của ứng dụng Spring Vault ở runtime.

~~~bash
# Tạo engine tại mount được chọn (chỉ làm một lần).
vault secrets enable -path=ssh-client-signer ssh

# Tạo SSH CA signing key tại Vault và nhận public key CA.
vault write ssh-client-signer/config/ca generate_signing_key=true

# Đọc public key CA để phân phối qua kênh quản trị đáng tin cậy.
vault read -format=raw ssh-client-signer/public_key
~~~

Role giới hạn SSH user certificate cho account `deploy`. Ở ví dụ này, chỉ cho phép PTY khi cần tương tác; không tự mở agent forwarding hoặc port forwarding:

~~~bash
vault write ssh-client-signer/roles/deploy-user - <<'JSON'
{
  "key_type": "ca",
  "allow_user_certificates": true,
  "allow_host_certificates": false,
  "allowed_users": "deploy",
  "default_user": "deploy",
  "ttl": "15m",
  "max_ttl": "1h",
  "default_extensions": {
    "permit-pty": ""
  },
  "allowed_extensions": "permit-pty",
  "allow_empty_principals": false,
  "allow_user_key_ids": false
}
JSON
~~~

Giới hạn role cần được thẩm định theo mô hình truy cập thật; role có `allowed_users="*"`, `allow_empty_principals=true` hoặc cho phép mọi extension sẽ tăng rủi ro. Vault role kiểm soát những gì CA **được phép ký**, còn máy chủ đích kiểm tra chứng thư và thực thi quyền ở tầng OpenSSH/OS.

Máy chủ Linux muốn tin SSH CA user key phải được quản trị viên phân phối **public key của CA** vào file chỉ đọc thích hợp, ví dụ:

~~~text
# /etc/ssh/sshd_config
TrustedUserCAKeys /etc/ssh/trusted-user-ca-keys.pub
~~~

Với user certificate, OpenSSH thường đối chiếu principal với tài khoản đăng nhập; triển khai phức tạp hơn có thể dùng `AuthorizedPrincipalsFile` hoặc `AuthorizedPrincipalsCommand` để giới hạn danh tính. Sau khi cấu hình, quản trị viên phải chạy `sshd -t` để kiểm tra cú pháp và reload/restart `sshd` theo cơ chế hệ điều hành, đồng thời giữ kênh quản trị dự phòng để tránh tự khóa truy cập.

**Trust của SSH CA phải được phân phối trước khi ứng dụng thử đăng nhập.** Chỉ cấu hình Vault signer mà chưa cấu hình `sshd` sẽ khiến chứng thư được cấp nhưng bị server từ chối.

### Phân quyền Vault theo workload

Ví dụ policy cho đúng một endpoint ký:

~~~hcl
path "ssh-client-signer/sign/deploy-user" {
  capabilities = ["create", "update"]
}
~~~

Đây là policy giới hạn đường dẫn. Với các endpoint `POST`, các bản Vault thường yêu cầu capability `update`; tài liệu HTTP SSH API cũng đề cập `create` và `update` cho thao tác ký. Vì vậy, ví dụ thể hiện cả hai capability **trên đúng path được giao**, không cấp quyền quản trị mount, CA hoặc role. Trong môi trường thực tế, kiểm thử policy với phiên bản Vault đang vận hành để xác định tập quyền nhỏ nhất đủ cho endpoint.

Không đưa Vault token vào YAML cấu hình ứng dụng hoặc Git. Cấu hình workload auth (như Kubernetes auth/AppRole) và session management của Spring Vault phải bảo đảm caller có token hợp lệ, tự xử lý token hết hạn theo mô hình đã chọn và ghi nhận lỗi xác thực một cách an toàn.

## 5. Thực hành gọi SSH signing bằng Vault CLI

Trên máy client (ví dụ máy chạy automation), tạo cặp khóa SSH riêng nếu chưa có. Không dùng `ssh-keygen` để ghi đè file khóa đang sử dụng.

~~~bash
# Tạo khóa test; ssh-keygen có thể hỏi passphrase tương tác.
ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519_deploy" -C "deploy-lab"

# Gửi PUBLIC KEY, nhận CHỨNG THƯ SSH (không phải private key).
vault write -field=signed_key ssh-client-signer/sign/deploy-user \
  public_key=@"$HOME/.ssh/id_ed25519_deploy.pub" \
  valid_principals=deploy \
  cert_type=user \
  ttl=15m \
  > "$HOME/.ssh/id_ed25519_deploy-cert.pub"

# Kiểm tra certificate type, principal, signing CA, validity và extensions.
ssh-keygen -Lf "$HOME/.ssh/id_ed25519_deploy-cert.pub"

# Chỉ thử với host đã cấu hình TrustedUserCAKeys cho signer này.
ssh -i "$HOME/.ssh/id_ed25519_deploy" \
  -o CertificateFile="$HOME/.ssh/id_ed25519_deploy-cert.pub" \
  deploy@server.example.internal
~~~

Tên file hậu tố `-cert.pub` giúp OpenSSH có thể tự nhận biết chứng thư tương ứng private key; ở đây chỉ định `CertificateFile` rõ ràng để tránh phụ thuộc việc tự phát hiện. Chứng thư SSH là dữ liệu public, nhưng file private key `id_ed25519_deploy` phải được bảo vệ nghiêm ngặt; passphrase và SSH agent cần theo chính sách workload.

Nếu dùng lệnh chỉ chạy tác vụ tự động không tương tác, cần xem xét việc cấp `permit-pty` có thật sự cần thiết không. Không tự bật agent forwarding, X11 forwarding hoặc port forwarding nếu chức năng triển khai không sử dụng.

### Kiểm tra khi SSH thất bại

Một response Vault 200 cùng `data.signed_key` **không bảo đảm** đăng nhập thành công. Nếu `ssh` trả `Permission denied (publickey)`:

- Đọc output `ssh-keygen -Lf` để xác minh hiệu lực, principal `deploy`, CA và extensions.
- Xác nhận private key thực dùng tương ứng public key đã gửi Vault ký.
- Kiểm tra `TrustedUserCAKeys` và cấu hình `sshd` ở **đúng máy chủ**, không nhầm CA của SSH host certificate.
- Kiểm tra account `deploy`, quy định `AuthorizedPrincipalsFile` và log `sshd` tại thời điểm từ chối.
- Dùng `ssh -vvv` để xem quá trình chọn identity/certificate; hạn chế chia sẻ log chứa thông tin cấu hình nội bộ.

Nếu client báo `REMOTE HOST IDENTIFICATION HAS CHANGED` hoặc lỗi host key verification, đó là **xác thực máy chủ SSH**, không phải kết luận role user signing sai. Cần kiểm tra CA/host key/known_hosts ở phía client, không tắt `StrictHostKeyChecking` chỉ để cho kết nối chạy.

## 6. Java + Spring Vault: gọi theo hợp đồng endpoint

Spring Vault cung cấp `VaultTemplate`/`VaultOperations` cho các API Vault; trong các phiên bản Spring Vault phổ biến, không có API nghiệp vụ SSH signing dạng `opsForSsh()` giống `opsForPki()`. Ta dùng `VaultOperations.write(path, request)` để gửi JSON đến endpoint của SSH engine.

Ví dụ dùng Java 17+ và Spring. Giả sử bean `VaultOperations` đã được cấu hình **đúng Vault server, TLS và workload authentication**; `publicKeyOpenSsh` là chuỗi thực đọc từ file public key hoặc nhận từ thành phần quản lý khóa:

~~~java
import java.util.Map;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class SshCertificateSigningService {

    // Chỉ role/mount đã được quản trị cấp cho workload.
    private static final String SIGN_PATH =
            "ssh-client-signer/sign/deploy-user";

    private final VaultOperations vault;

    public SshCertificateSigningService(VaultOperations vault) {
        this.vault = vault;
    }

    public SignedSshCertificate signDeployUser(String publicKeyOpenSsh) {
        Objects.requireNonNull(publicKeyOpenSsh, "publicKeyOpenSsh");
        if (publicKeyOpenSsh.isBlank()) {
            throw new IllegalArgumentException("SSH public key không được rỗng");
        }

        // Server Vault thực thi giới hạn role và policy:
        // valid_principals/ttl không được để bên gọi tùy ý leo thang.
        Map<String, Object> request = Map.of(
                "public_key", publicKeyOpenSsh,
                "valid_principals", "deploy",
                "cert_type", "user",
                "ttl", "15m");

        // VaultTemplate tự quản lý API prefix /v1/, endpoint và token.
        VaultResponse response = vault.write(SIGN_PATH, request);
        Map<String, Object> data =
                response == null ? null : response.getData();
        if (data == null) {
            throw new IllegalStateException("Vault SSH sign thiếu data");
        }

        Object signed = data.get("signed_key");
        if (!(signed instanceof String cert) || cert.isBlank()) {
            throw new IllegalStateException(
                    "Vault SSH sign thiếu data.signed_key");
        }

        Object serial = data.get("serial_number");
        String serialNumber = serial == null ? "" : serial.toString();

        return new SignedSshCertificate(cert, serialNumber);
    }

    public record SignedSshCertificate(
            String signedKey, String serialNumber) {
    }
}
~~~

Ghi chú về ví dụ:

- **Không** tự ghép `/v1/` vào `SIGN_PATH`: `VaultTemplate` xử lý tiền tố API và endpoint đã cấu hình.
- **Không** tự thêm `X-Vault-Token` vào JSON hay log token; Spring Vault sử dụng session/token từ cơ chế auth.
- Request chỉ chứa public key, principal, cert type và TTL **đã được cố định theo hợp đồng nghiệp vụ**; role Vault kiểm tra một lần nữa.
- `VaultResponse.getData()` chứa `signed_key` (chuỗi OpenSSH certificate) và `serial_number`; không ép dữ liệu thành X.509 `CertificateBundle`.
- Nếu `vault.write(...)` ném exception do lỗi Vault/TLS/quyền, **không** biến lỗi đó thành “cert không hợp lệ” hoặc trả chứng thư cũ đã hết hạn một cách im lặng.
- Response chỉ nên đi đến thành phần thực hiện SSH; nếu lưu vào secret store, cần gắn TTL/expiration và cơ chế cleanup. Không ghi private key vào cùng log/request.

Sau khi nhận response, thành phần điều phối lưu `signedKey` vào file certificate được phân quyền phù hợp và ghép với **private key tương ứng** có sẵn. Việc biến chuỗi thành file để OpenSSH dùng, kiểm tra fingerprint/principals, gọi SSH và triển khai dự phòng là trách nhiệm của hệ thống vận hành — `VaultTemplate.write` không trực tiếp thực hiện đăng nhập SSH.

### Phân loại lỗi theo từng tầng

| Tầng | Lỗi | Cách hiểu và xử lý |
| --- | --- | --- |
| Client Java | Public key rỗng hoặc chuỗi không đúng định dạng | Validate đầu vào trước khi gọi; không retry dữ liệu sai |
| Vault auth/ACL | HTTP 403 | Token/workload auth hoặc policy thiếu quyền; kiểm tra chính xác `ssh-client-signer/sign/deploy-user` |
| Vault request/role | HTTP 400 | Public key, principal, cert type, TTL, critical options/extension không phù hợp role |
| Vault path | HTTP 404 | Nhầm mount hoặc role không tồn tại; đối chiếu lại path hợp đồng |
| Vault availability | Timeout, 429, 5xx | Retry giới hạn có backoff/jitter; phát cảnh báo, không tạo file cert rỗng |
| OpenSSH server | `Permission denied (publickey)` | CA trust, principal, thời hạn, private key tương ứng hoặc chính sách SSH server |
| OpenSSH client | Host key/certificate verification lỗi | Kiểm tra host CA, known_hosts và hostname; không bỏ qua xác thực host |

Với endpoint ký, mỗi lần gọi có thể tạo **chứng thư mới với serial mới**. Vì vậy retry sau timeout không bảo đảm idempotent: request đầu có thể đã ký xong nhưng response thất lạc. Giới hạn số retry, ghi correlation/request ID khi có, và tránh hiểu việc có hai cert cùng public key là hai danh tính độc lập.

## 7. Vì sao hợp đồng của role quan trọng hơn JSON đầu vào?

HTTP API cho phép caller đề xuất `ttl`, `valid_principals`, `extensions` hoặc `key_id`, nhưng role Vault phải là nơi ra quyết định cuối cùng. Xem một số cấu hình có rủi ro:

| Thiết kế | Rủi ro | Cách giới hạn |
| --- | --- | --- |
| Role cho `allowed_users=*` | Workload bị lộ có thể thử yêu cầu principal đặc quyền | Tạo role riêng cho account/nhóm nhiệm vụ và gắn Vault policy tương ứng |
| `allow_empty_principals=true` | Cert không chỉ rõ danh tính cần xác thực | Giữ `false`; yêu cầu principal cụ thể |
| Caller tùy ý đặt `key_id` | Audit khó gắn chứng thư với workload thực | Để Vault gán token display name hoặc dùng `key_id_format` đã kiểm soát |
| Caller tự chọn mọi `extensions` | Có thể bật port/agent/X11 forwarding ngoài nhu cầu | Dùng `default_extensions` và giới hạn `allowed_extensions` |
| TTL quá dài | Chứng thư bị mất khó thu hồi hiệu quả | TTL ngắn, cấp lại theo phiên/lượt chạy, kiểm tra `valid_before` thực |
| CA user tin trên quá nhiều host | Một role bị lạm dụng ảnh hưởng phạm vi lớn | Tách CA/trust domain, dùng principal và quyền hệ điều hành tối thiểu |

SSH cert chứa thời gian hiệu lực riêng (ví dụ `valid_after`/`valid_before`) và chữ ký CA. Đừng coi khả năng gia hạn **Vault token** hoặc **Vault lease** là cách kéo dài chứng thư SSH đã cấp; khi cần thời hạn mới, phải lấy chứng thư mới. Cơ chế thu hồi ngoài chứng thư ngắn hạn phụ thuộc OpenSSH (ví dụ KRL hoặc đổi CA/trust), không nên giả định gọi revoke Vault token sẽ ngay lập tức làm máy chủ từ chối cert đã được ký.

Trong production, nên quy định vòng đời:

1. Xác định thời gian thực tế job cần kết nối SSH.
2. Cấp chứng thư ngay trước khi sử dụng, có đủ biên an toàn.
3. Kiểm tra cert được ký đúng principal/role và còn hiệu lực ở thời điểm bắt đầu lẫn khi kết nối lại.
4. Không tái dùng private key/cert rộng rãi giữa các workload không cùng danh tính hoặc quyền.
5. Thu hồi/loại bỏ file cert khỏi workspace sau job; nếu có nghi vấn lộ private key, thực hiện quy trình ứng cứu và cô lập danh tính.

## 8. Kiểm thử tích hợp và giám sát

Lab kiểm thử cần có Vault test instance đã mount SSH engine, role/policy test, một OpenSSH server được cấu hình tin CA test và một keypair test. Tách account quản trị CA khỏi workload chỉ ký chứng thư.

| Trường hợp | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Sign thành công | Gửi public key hợp lệ, principal `deploy`, TTL 15m | Response có `data.signed_key` và serial; `ssh-keygen -Lf` đọc được |
| Không có quyền | Token chỉ được đọc KV, gọi `/sign/deploy-user` | Vault từ chối 403, không có cert để sử dụng |
| Principal vượt role | Gửi `valid_principals=root` cho role chỉ cho `deploy` | Vault từ chối/không cấp cert cho quyền ngoài role |
| TTL vượt ngưỡng | Gửi TTL vượt `max_ttl` | Request bị chặn hoặc bị giới hạn theo hợp đồng API/version; kiểm tra hiệu lực thực |
| Khóa sai định dạng | Gửi chuỗi không phải public key OpenSSH | Vault trả lỗi; client không ghi file cert giả |
| SSH trust chưa cấu hình | Vault cấp cert nhưng `sshd` chưa tin CA | Đăng nhập bị từ chối dù sign API đã thành công |
| Principal không khớp | Ký cho `deploy` nhưng kết nối bằng user khác | Đăng nhập bị từ chối theo chính sách principal/server |
| Private key khác | Dùng cert ký cho key A nhưng chứng minh sở hữu key B | SSH authentication thất bại |
| Hết hạn chứng thư | Thử đăng nhập lại sau `valid_before` | OpenSSH từ chối cert; cấp lại theo policy |
| Vault mất kết nối | Simulate timeout/5xx khi sign | Ứng dụng báo lỗi có phân loại, retry hữu hạn; không log token/private key |

Trong giám sát, nên có số lần `sign` thành công/thất bại theo role, tỉ lệ lỗi 4xx/5xx, latency, thời gian hiệu lực cert đầu ra, kết quả SSH auth cuối cùng và số request retry. Có thể gắn `request_id` từ Vault với mã job, kèm serial number để truy dấu mà không lưu raw token/private key.

Các tên metric như `ssh_sign_request_total`, `ssh_sign_failure_total`, `ssh_certificate_remaining_seconds` là **đề xuất cho ứng dụng Micrometer**, không phải metric mặc định mà Spring Vault chắc chắn cung cấp. Không log nguyên public key nếu nó chứa thông tin định danh không cần thiết; log fingerprint và role theo chính sách tổ chức.

## 9. Khi ký SSH host key thay vì user key

Trường hợp cần máy khách xác thực chính máy chủ SSH, nên sử dụng SSH host certificate. Quản trị viên có thể mount signer riêng ở `ssh-host-signer/`, role chỉ cho phép host certificates và giới hạn domain:

~~~bash
# Chạy bởi quản trị viên; giả định mount/CA đã tồn tại.
vault write ssh-host-signer/roles/hosts \
  key_type=ca \
  allow_host_certificates=true \
  allow_user_certificates=false \
  allowed_domains=example.internal \
  allow_subdomains=true \
  ttl=24h

# SSH host cần gửi PUBLIC KEY để Vault ký chứng thư loại host.
vault write ssh-host-signer/sign/hosts \
  cert_type=host \
  public_key=@/etc/ssh/ssh_host_ed25519_key.pub \
  valid_principals=server.example.internal
~~~

Sau khi nhận `signed_key`, máy chủ cấu hình `HostCertificate` tương ứng với `HostKey`; các client tin SSH CA host bằng mục `@cert-authority` trong `known_hosts`, theo domain được duyệt. Nếu hostname/SNI hoặc principal không khớp, khách sẽ không tự động chấp nhận máy chủ. Hợp đồng endpoint ký vẫn là `POST /<mount>/sign/<role>`, nhưng policy, role, `cert_type`, principal và bên lưu chứng thư khác với user signing.

## 10. Ghi nhớ và tự kiểm tra

**SSH signing là một hợp đồng giữa ba nơi**: Vault kiểm soát quyền ký theo endpoint và role; Spring Vault gửi yêu cầu JSON chính xác và xử lý `data.signed_key`; OpenSSH quyết định cuối cùng có chấp nhận chứng thư dựa trên CA trust, principal, thời hạn và policy máy chủ hay không. Chứng thư SSH dùng cho OpenSSH, không thay thế chứng thư X.509 của TLS.

Hãy thử trả lời:

1. Vì sao gửi `public_key` đến Vault SSH signer không làm lộ private key, và lúc đăng nhập private key vẫn cần thiết?
2. Trong `VaultTemplate.write`, vì sao dùng `ssh-client-signer/sign/deploy-user` thay cho `/v1/ssh-client-signer/sign/deploy-user`?
3. Vì sao đặt `valid_principals=deploy` trong request **chưa đủ** để đảm bảo server cho phép SSH?
4. Vault trả `data.signed_key` nhưng `ssh` báo `Permission denied`: cần kiểm tra những lớp nào?
5. Những quyền nào cần tách giữa administrator của SSH CA, người quản lý role và workload chỉ được ký?
6. Khi Vault token bị thu hồi sau khi cert đã ký, có thể kết luận SSH cert đó lập tức vô hiệu ở mọi máy chủ không? Vì sao?

### Tài liệu tham khảo

- [HashiCorp Vault — SSH secrets engine](https://developer.hashicorp.com/vault/docs/secrets/ssh)
- [HashiCorp Vault — Signed SSH certificates](https://developer.hashicorp.com/vault/docs/secrets/ssh/signed-ssh-certificates)
- [HashiCorp Vault — SSH secrets engine HTTP API](https://developer.hashicorp.com/vault/api-docs/secret/ssh)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Vault — Vault client access và xử lý lỗi](https://docs.spring.io/spring-vault/reference/vault/vault-client.html)
