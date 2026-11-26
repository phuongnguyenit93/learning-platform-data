# Kiểm soát nơi cung cấp mật khẩu, token và khóa riêng trong Spring Vault

Trong ứng dụng Java sử dụng **Spring Vault** để truy cập **HashiCorp Vault**, an toàn của bí mật phụ thuộc nhiều vào *nguồn cấp* và *đường đi của credential* hơn là tên thuật toán mã hóa. Một mật khẩu cơ sở dữ liệu được lấy từ Vault vẫn có thể bị lộ nếu ứng dụng in nó vào log. Một Vault token có TTL ngắn vẫn có thể bị sử dụng trái phép nếu được gắn sẵn vào image. Một chứng chỉ TLS hợp lệ cũng không bảo vệ được workload nếu **private key** đi kèm được sao chép vào repository.

Bài học thuộc chương **Chứng thư và tài khoản** và tập trung vào câu hỏi: **ai cấp mật khẩu, token, private key; cung cấp bằng kênh nào; được phép lưu ở đâu, trong bao lâu và ai có quyền đọc?** Kiến thức này kết nối trực tiếp với cơ chế xác thực theo workload, `VaultTemplate`, chính sách phân quyền, KV secrets, dynamic credentials và lease, Transit encryption, PKI, xử lý lỗi, giám sát và kiểm thử tích hợp của module **SPRING_VAULT**.

## 1. Phân biệt nguồn cấp, nơi lưu và nơi sử dụng

Một credential đi qua nhiều điểm. Đặt câu hỏi “credential được lưu ở Vault chưa?” là chưa đủ: credential vẫn phải được cấp cho ứng dụng bằng một cơ chế cụ thể.

| Thành phần | Ý nghĩa | Câu hỏi kiểm tra |
| --- | --- | --- |
| **Nguồn cấp (issuer/source)** | Thành phần tạo hoặc cung cấp credential: Vault, identity provider, metadata server, CA, hệ thống IAM, quản trị viên. | Ai chịu trách nhiệm cấp và thu hồi? |
| **Kênh vận chuyển (delivery channel)** | HTTPS có TLS, API nội bộ, Unix socket, tệp mount, agent template, biến môi trường... | Ai có thể quan sát/chặn/sửa dữ liệu trên đường đi? |
| **Vùng lưu tạm (storage/sink)** | Bộ nhớ tiến trình, file trên volume, keystore, secret store, environment, cache. | Credential tồn tại ở đâu, quyền đọc và thời gian tồn tại thế nào? |
| **Bên sử dụng (consumer)** | HTTP client gọi Vault, JDBC pool, TLS engine, ký JWT, mã hóa dữ liệu... | Quyền truy cập có đúng mục đích không? |
| **Vòng đời (lifecycle)** | Phát hành, phân phối, sử dụng, renew/rotate, revoke, xóa an toàn. | Khi thay người/máy/ứng dụng, làm sao cắt quyền? |

Ví dụ, chuỗi `Vault → HTTPS → Java heap → JDBC pool` chứa ít nhất bốn ranh giới bảo mật. Mỗi ranh giới cần có chủ sở hữu, cơ chế xác thực và giới hạn quyền.

**Ba nguyên tắc cốt lõi:**

1. **Không đưa credential cấp cao cố định vào ứng dụng để đổi lấy credential cấp thấp.** Ưu tiên identity theo workload như Kubernetes, GCP, AWS hoặc chứng chỉ client nếu hệ thống hỗ trợ.
2. **Cấp bí mật đúng nơi dùng với quyền và thời hạn tối thiểu.** Credential được cấp cho một ứng dụng không nên dùng chung với toàn bộ máy chủ hoặc mọi namespace.
3. **Giảm số bản sao và thời gian tồn tại của bí mật.** Secrets trong file, log, heap dump, telemetry, image, build cache hay lịch sử shell đều là các bản sao cần quản lý.

## 2. Sơ đồ đường đi của credential

~~~mermaid
flowchart TD
    W["Workload identity<br/>Kubernetes JWT / Cloud identity / mTLS"] --> A["Spring Vault ClientAuthentication"]
    A --> L["Vault auth method<br/>Kiểm danh tính + role"]
    L --> T["Vault client token<br/>Policy + TTL"]
    T --> V["VaultTemplate / HTTP API"]
    V --> K["KV: static secret"]
    V --> D["Database: dynamic username/password + lease"]
    V --> P["PKI: ký CSR / phát hành certificate"]
    V --> E["Transit: encrypt / decrypt / sign"]
    K --> C["Ứng dụng sử dụng trong bộ nhớ"]
    D --> C
    P --> F["TLS keystore / certificate files"]
    E --> C
    C --> S["Database / upstream service"]
~~~

Sơ đồ cũng cho thấy **bootstrap problem**: trước khi ứng dụng lấy secret từ Vault, nó cần chứng minh danh tính để nhận Vault token. Nếu giải pháp bootstrap là đặt sẵn một Vault token quyền cao vào source code, ta đã chuyển điểm yếu sang nơi cấp token. Một luồng tốt sử dụng chứng cứ sẵn có từ hạ tầng và chỉ cho workload hợp lệ đăng nhập.

### Phân biệt bốn nhóm bí mật

| Nhóm | Ví dụ | Nơi cấp phù hợp | Cách kiểm soát |
| --- | --- | --- | --- |
| Mật khẩu/tài khoản | Database password, API password | Vault KV hoặc engine cấp dynamic credential | Quyền đọc theo workload; rotation/lease; hạn chế bản sao |
| Credential truy cập Vault | Vault client token, service-account JWT dùng login | Vault phát token; nền tảng workload cấp JWT/identity | Token TTL, policy tối thiểu, renew/revoke, xác thực theo workload |
| Khóa riêng | TLS server key, client mTLS key, signing key | Sinh ngay tại nơi sử dụng hoặc bằng cơ chế khóa được quản lý | Không xuất key khi không cần; keystore/HSM/KMS; file permission |
| Chứng thư và trust material | X.509 cert, CA cert, truststore | PKI/CA | Xác minh chuỗi CA, SAN, EKU, hạn hiệu lực; quản lý lifecycle |

**Lưu ý:** chứng chỉ public và CA public không phải private key. Có thể phân phối CA certificate rộng hơn, nhưng phải kiểm tra *tính toàn vẹn và nguồn tin cậy*. Không nên cất mọi file `.pem` dưới cùng một chính sách nếu chúng chứa loại dữ liệu khác nhau.

## 3. Nguồn cấp credential nên được ưu tiên như thế nào?

### 3.1. Identity do hạ tầng cấp cho workload

Đối với Java chạy trên Kubernetes, ứng dụng có thể sử dụng **service-account JWT** được mount theo cơ chế chuẩn, để đăng nhập Vault bằng Kubernetes auth. JWT chứng minh workload thuộc service account/namespace được ràng buộc; Vault quyết định role và policy tương ứng.

Ví dụ luồng:

~~~text
Pod service account JWT
   → Vault auth/kubernetes/login
   → Vault client token với policy và TTL
   → VaultTemplate đọc đúng secret path
~~~

Đối với GCE, có thể dùng instance identity JWT từ metadata server; với AWS có thể dùng IAM-based identity; với một số kiến trúc khác dùng OIDC/JWT hoặc mTLS/cert authentication. Cơ chế nào phù hợp phụ thuộc nền tảng và trust boundary của hệ thống; không giả định mọi runtime đều truy cập metadata của GCE hay token Kubernetes.

**Quyền tối thiểu cho bootstrap:** Vault role phải giới hạn identity được chấp nhận, như service account, namespace, cloud account, project hoặc audience. Một JWT hợp lệ với nhà cung cấp danh tính không đồng nghĩa có quyền login vào mọi Vault role.

### 3.2. Cấp token thủ công: chỉ dùng khi có quy trình kiểm soát

Trong tình huống vận hành, ứng dụng legacy hoặc môi trường phát triển, đôi khi phải truyền Vault token trực tiếp. Khi đó:

- Cấp token theo policy tối thiểu, TTL ngắn và khả năng thu hồi rõ ràng; tách riêng token dev/staging/prod.
- Truyền qua kênh đã bảo vệ, tránh lưu token trong Git, Dockerfile `ARG`/`ENV`, container image, log build hoặc văn bản ticket.
- Xác định rõ ứng dụng đọc token từ biến môi trường, file hay secret manager, cách cấp quyền đọc và cách thay token.
- Không dùng **root token** của Vault làm credential chạy ứng dụng thường ngày.

Vault token trong biến môi trường *không tự động an toàn*: người có quyền xem môi trường tiến trình, crash dump hoặc cấu hình orchestration có thể lấy được. Tuy nhiên, một secret file cũng có rủi ro tương tự nếu quyền file/volume không chặt. Hãy đánh giá đường đi thực tế thay vì mặc định một kiểu truyền luôn an toàn hơn mọi kiểu khác.

### 3.3. Vault Agent hoặc CSI/sidecar cấp secret vào file

Có thể để một agent xác thực Vault, tự xử lý renew và render secret vào volume/file cho ứng dụng không tích hợp Vault API trực tiếp. Đây là mô hình khác với việc Spring Vault tự thực hiện `ClientAuthentication`.

Cần xác định rõ:

- Agent xác thực bằng identity nào; ai có quyền đọc token sink hoặc secret file?
- File nằm trên volume được giới hạn/`tmpfs` hay lưu lên đĩa bền vững?
- Quyền sở hữu, `chmod`, UID/GID và namespace của container nào có thể đọc?
- File được cập nhật/đổi mới theo cách nào? Ứng dụng có reload được không?
- Khi Pod/VM dừng, dữ liệu có được dọn dẹp và token có được revoke phù hợp không?

Không bật đồng thời nhiều đường cấp credential không có kiểm soát, vì ứng dụng có thể vô tình đọc **bản secret cũ** từ tệp cấu hình thay vì giá trị đang được cập nhật bởi agent.

## 4. Bảng quyết định nguồn cấp mật khẩu, token và private key

| Nhu cầu | Nguồn cấp khuyến nghị | Điểm cần tránh |
| --- | --- | --- |
| Java trên Kubernetes truy cập Vault | Workload identity/Kubernetes auth, Vault phát client token | Root token hardcode; dùng một service account cho nhiều ứng dụng không liên quan |
| Java trên GCE truy cập Vault | GCE identity từ metadata, Vault GCP GCE auth nếu phù hợp | Copy service-account private JSON key vào image |
| Đọc API key tĩnh | Vault KV với policy chính xác path và phiên bản secret | In secret vào startup logs; sao chép vào file cấu hình commit |
| Database credential có thể cấp động | Vault Database secrets engine và lease | Dùng chung mật khẩu DB vĩnh viễn, không xử lý expiry |
| TLS server cần private key | Sinh key trong workload/HSM và để PKI ký CSR khi khả thi | Truyền private key qua nhiều hệ thống, lưu key chung repository |
| Mã hóa dữ liệu nghiệp vụ | Vault Transit hoặc dịch vụ quản lý khóa, khóa không export khi không cần | Tự kéo khóa mã hóa lâu dài về ứng dụng và ghi log |
| Client mTLS đến upstream | Certificate + private key theo identity của workload; keystore được bảo vệ | Dùng chung private key trên nhiều dịch vụ, không luân chuyển |
| Máy phát triển | Auth riêng cho dev với scope hẹp, profile riêng | Mượn Vault token production rồi dán vào `application.yml` |

**Phân biệt rõ:** **TLS truststore** chứa chứng chỉ CA/public material để xác minh đối tác; **keystore** có thể chứa private key và certificate chain để workload chứng minh danh tính. Quyền truy cập keystore chứa private key phải chặt hơn quyền đọc một bundle CA công khai.

## 5. Thiết kế cụ thể cho Spring Cloud Vault và VaultTemplate

### 5.1. Bootstrap bằng Kubernetes auth thay cho token tĩnh

Ví dụ cấu hình minh họa cho ứng dụng dùng **Spring Boot + Spring Cloud Vault** có hỗ trợ Config Data API:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: KUBERNETES
      kubernetes:
        role: orders-service
        service-account-token-file: /var/run/secrets/kubernetes.io/serviceaccount/token
      kv:
        enabled: true
        backend: secret
        application-name: orders-api
~~~

Để luồng này hoạt động, Vault Kubernetes auth method cần được thiết lập và role `orders-service` phải cho phép **đúng Kubernetes service account/namespace** của ứng dụng. Cấu hình SSL/truststore Java phải xác minh CA của Vault. Đường dẫn và tên thuộc tính phụ thuộc phiên bản Spring Cloud Vault; ứng dụng dùng riêng `spring-vault-core` phải tự tạo `ClientAuthentication` và `SessionManager` phù hợp.

Với mô hình này, trình tự cơ bản là:

1. Kubernetes cấp token nhận diện workload trong volume được bảo vệ.
2. Spring Vault dùng token nhận diện để đăng nhập Vault theo role.
3. Vault phát client token với policy, TTL và khả năng renew do Vault kiểm soát.
4. `VaultTemplate` gửi yêu cầu tới secret engine với Vault token được quản lý bởi session.

Không cần đưa `spring.cloud.vault.token` hay root token vào image. **Nếu service-account JWT bị sao chép**, bên tấn công có thể thử tái sử dụng nó tùy thời hạn/audience/role; vì vậy JWT bootstrap vẫn là credential nhạy cảm.

### 5.2. Ví dụ policy đúng giới hạn đường secret

Một ứng dụng cần đọc đúng secret `orders/config` từ KV v2 tại mount `secret/`:

~~~hcl
path "secret/data/orders/config" {
  capabilities = ["read"]
}
~~~

Với KV v2, path dùng để kiểm tra policy có thành phần `data`; còn path logic của API Spring Vault khi gọi `opsForKeyValue` có thể là `orders/config`. Không cấp `secret/*` chỉ vì đọc bị `403`: trước tiên xác nhận mount, KV version, path, identity và policy gắn vào token.

Ví dụ `VaultTemplate` đọc dữ liệu mà không xuất secret ra log:

~~~java
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersConfigReader {

    private final VaultTemplate vaultTemplate;

    public OrdersConfigReader(VaultTemplate vaultTemplate) {
        this.vaultTemplate = vaultTemplate;
    }

    public Map<String, Object> read() {
        VaultResponse response = vaultTemplate
            .opsForKeyValue("secret", KeyValueBackend.KV_2)
            .get("orders/config");

        if (response == null || response.getData() == null) {
            throw new IllegalStateException("Missing Vault configuration");
        }
        return response.getData();
    }
}
~~~

Trong ví dụ này `read()` trả về dữ liệu nhạy cảm: bên gọi phải biết rõ dữ liệu được chuyển đến đâu, có được cache không và có bị ghi log/serialize ra HTTP response hay không. Tránh tạo thêm bản sao không cần thiết.

### 5.3. Lấy database password động

Với Vault Database secrets engine, đường ví dụ `database/creds/orders-reader` có thể tạo một cặp `username/password` theo role và lease:

~~~hcl
path "database/creds/orders-reader" {
  capabilities = ["read"]
}
~~~

Một lời gọi thử bằng Vault API:

~~~http
GET /v1/database/creds/orders-reader
X-Vault-Token: <Vault client token>
~~~

Phản hồi thường có `data.username`, `data.password`, `lease_id`, `lease_duration` và `renewable` tùy engine/role. Trong Java, có thể đọc response từ `VaultTemplate` rồi cung cấp credential trực tiếp cho thành phần JDBC hoặc pool được thiết kế để quản lý lifecycle; **không in password hoặc full response**. Cần chú ý:

- Mỗi lần tạo dynamic credential có thể phát sinh account DB và lease riêng. **Không gọi endpoint tạo credential cho mọi HTTP request** nếu không có cơ chế quản lý vòng đời phù hợp.
- Khi lease hết hạn/revoke, kết nối mới có thể thất bại; pool cần chiến lược thay username/password và thay connection.
- Nếu engine cho phép renew, thiết lập renewal theo TTL thực tế; nếu không renew được, cấp credential mới trước hạn.
- `Vault client token TTL` và `dynamic secret lease TTL` độc lập; việc token còn hạn không đồng nghĩa DB credential luôn còn hiệu lực.

**Độ chính xác của nguồn cấp:** trong trường hợp này Vault không chỉ “lưu mật khẩu DB tĩnh”, mà tương tác với database để cấp credential động theo role. Điều đó cho phép thu hồi và giảm phạm vi ảnh hưởng khi credential bị lộ.

## 6. Private key của TLS/mTLS và Vault PKI

Private key là bí mật chứng minh danh tính và có thể được dùng để ký hoặc giải mã tùy thuật toán. Khác với certificate và CA bundle, key không nên được sao chép qua các hệ thống nếu nhu cầu chỉ là **xin CA ký chứng chỉ**.

### 6.1. Hai mô hình phát hành chứng chỉ

| Mô hình | Key được tạo ở đâu? | Điều cần đánh giá |
| --- | --- | --- |
| **Vault PKI `issue/<role>`** | Vault có thể tạo key pair và trả cả certificate/private key cho client. | Response chứa private key: bảo vệ transport, log, memory, storage và quyền đọc. |
| **CSR + Vault PKI `sign/<role>`** | Workload tạo private key tại nơi dùng; chỉ gửi CSR tới Vault. | Private key không cần rời nơi tạo; quản lý key và việc tự động hóa CSR/rotation tại client. |

Nếu workload kiểm soát được quá trình tạo khóa, **CSR signing** thường giúp giảm số nơi private key phải xuất hiện. Nhưng mô hình `issue` có thể hữu ích cho client không tự tạo CSR; cần bảo vệ response chứa key tương ứng.

### 6.2. Ví dụ tạo khóa cục bộ và gửi CSR

Ví dụ sử dụng OpenSSL trên môi trường được cấp quyền phù hợp:

~~~bash
# /run/identity nên là volume có quyền đọc giới hạn, ưu tiên tmpfs.
umask 077

openssl genpkey -algorithm RSA \
  -pkeyopt rsa_keygen_bits:3072 \
  -out /run/identity/orders-api.key

openssl req -new \
  -key /run/identity/orders-api.key \
  -subj "/CN=orders-api.internal.example" \
  -addext "subjectAltName=DNS:orders-api.internal.example" \
  -out /run/identity/orders-api.csr

# Cần Vault token đã được cấp qua auth workload phù hợp.
vault write -format=json \
  pki_int/sign/orders-server \
  csr=@/run/identity/orders-api.csr \
  ttl="24h" \
  > /run/identity/orders-api-cert-response.json
~~~

Ở lệnh trên, `orders-api.key` **không được gửi** đến Vault; endpoint `sign` nhận CSR và trả certificate/certificate chain (không cần trả private key). Cần cấu hình role `orders-server` chấp nhận tên DNS và SAN mong muốn; kiểm tra role PKI, issuer, maximum TTL và thuật toán phù hợp. Nếu chạy trong container, bảo vệ quyền đọc file key và certificate response; đừng để private key trong image hoặc artifact của pipeline.

Sau khi ký, TLS runtime cần **certificate + matching private key**; client cần tin CA/chain đúng. Một certificate không khớp private key sẽ khiến TLS handshake thất bại. Lệnh trên chỉ minh họa bước tạo và ký; tích hợp vào Java JSSE/PKCS12 và reload cert phụ thuộc runtime đã chọn.

### 6.3. Keystore, truststore, HSM và khóa không xuất

- **Truststore** chứa trust anchor/certificate dùng xác minh đối tác. Kiểm soát cập nhật CA để tránh bị thêm CA giả.
- **Keystore có private key** phải được bảo vệ bằng quyền file, ACL, mật khẩu/key management phù hợp, lưu trữ được mã hóa và cơ chế tránh lộ qua backup.
- **HSM/KMS hoặc cơ chế khóa không export** giúp giới hạn nơi key xuất hiện; nhưng muốn dùng cho TLS/Java cần provider/integration tương thích với thuật toán và runtime.
- **Vault Transit** thường cho phép ứng dụng gửi dữ liệu để mã hóa, giải mã, ký hoặc xác minh mà không phải tải material của key về JVM. Dùng Transit cho nghiệp vụ mã hóa/ký khi phù hợp, **không mặc định Transit là một TLS keystore**.

### 6.4. Rotation chứng chỉ không chỉ là thay file

Luân chuyển certificate/private key cần tính đến tiến trình Java **đã tải keystore từ trước**. Ghi đè file trên volume chưa chắc khiến kết nối mới dùng certificate mới. Cần cơ chế reload `SSLContext`/keystore, rolling restart hoặc giải pháp hỗ trợ reload; test cả phía client và server. Khi chuyển CA, cân nhắc giai đoạn tin cậy chồng lấn để tránh ngắt kết nối, đồng thời có quy trình loại CA cũ sau chuyển đổi.

## 7. Nơi cấp credential: môi trường triển khai và rủi ro

| Vị trí truyền/lưu | Ưu điểm thực dụng | Rủi ro phải kiểm soát |
| --- | --- | --- |
| **Biến môi trường** | Dễ tích hợp ứng dụng legacy và cấu hình container. | Tiến trình, debug, crash dump, log/env inspection và biến được kế thừa sang process con. |
| **Command-line argument** | Dễ tự động hóa nhưng khó bảo vệ. | Có thể hiện trong process listing, shell history, logs của orchestrator. |
| **Tệp cấu hình/secret file** | Có ACL, có thể mount read-only, thuận tiện cho cert/key. | Quyền file, sao lưu, thời gian tồn tại, thay file không tự reload. |
| **Container image/repository** | Dễ build, nhưng không nên chứa secret. | Secret bị sao chép vào layer, cache, registry, Git history và bản sao CI/CD. |
| **Kubernetes Secret** | API có RBAC, mount dưới dạng file/env. | Cần kiểm soát RBAC, lưu trữ/etcd, quyền Pod; env không tự cập nhật khi Secret đổi. |
| **Vault Agent template/CSI** | Có thể cập nhật secret tại runtime; giảm code dùng API. | Cấu hình sink, quyền file, refresh/reload, lỗi agent và bản secret cũ. |
| **Lấy trực tiếp qua Spring Vault** | Client quản lý auth/session và nhận credential khi cần. | Truststore, scope token, heap/cache, lease/renewal, network dependency. |
| **HSM/KMS** | Có thể giữ key material ngoài bộ nhớ ứng dụng. | Quyền gọi key operations, availability, audit, hạn mức và tích hợp runtime. |

**Không có “nơi lưu an toàn tuyệt đối”.** Thay vì lựa chọn theo khẩu hiệu, lập một bản đồ dữ liệu: credential nào, ai cấp, ai đọc, ở đâu, TTL bao lâu, cơ chế thu hồi nào và bản sao nào còn tồn tại sau khi workload dừng.

### Phân biệt file-based và env-based delivery trong Kubernetes

Một `Secret` mount thành volume có thể được Kubernetes cập nhật theo cơ chế tương ứng; một biến môi trường lấy từ `Secret` thường chỉ được thiết lập **khi container bắt đầu**, nên không tự đổi trong tiến trình đang chạy. Với `subPath` mount, khả năng cập nhật có hạn chế riêng. Ngay cả khi file đã thay đổi, ứng dụng Java vẫn cần biết reload cấu hình, pool hoặc key material.

Không lưu credential vào `ConfigMap` vì ConfigMap không được thiết kế như tài nguyên secret. Đối với Kubernetes Secret, cần cấu hình RBAC, encryption at rest và quyền truy cập Pod/namespace phù hợp; tên “Secret” không thay thế việc quản trị quyền.

## 8. Tránh làm lộ credential trong ứng dụng Java

Các đường rò rỉ hay gặp:

1. **Log HTTP debug:** interceptor ghi `X-Vault-Token`, `Authorization`, `jwt` từ login request, body chứa `private_key` hoặc secret data.
2. **Exception message/trace:** mã của ứng dụng in cả response hoặc request khi API thất bại; một số thư viện có thể kèm payload trong lỗi.
3. **Spring Actuator/config endpoints:** cấu hình hoặc nguồn thuộc tính chứa secret bị expose ngoài phạm vi cần thiết; không dựa hoàn toàn vào mask mặc định.
4. **Serialization:** controller vô tình trả đối tượng DTO chứa mật khẩu/certificate key hoặc gửi lên metrics/tracing.
5. **Heap dump và memory snapshot:** password dạng `String` có thể tồn tại đến khi GC dọn; `char[]` có thể xóa sau khi dùng nhưng còn phụ thuộc API downstream và bản sao trung gian.
6. **Build/CI/CD:** token nằm trong log pipeline, artifact, environment dump, `docker history` hoặc command line của job.

Ví dụ không nên làm:

~~~java
VaultResponse response = vaultTemplate.read("database/creds/orders-reader");
// Sai: response có thể chứa username/password và metadata nhạy cảm.
logger.info("Vault response: {}", response);
~~~

Thay bằng telemetry chỉ chứa thông tin đủ chẩn đoán:

~~~java
long start = System.nanoTime();
try {
    VaultResponse response = vaultTemplate.read("database/creds/orders-reader");
    if (response == null || response.getData() == null) {
        throw new IllegalStateException("Vault returned no credential data");
    }
    logger.info("Vault credential request succeeded, role={}", "orders-reader");
    // Chuyển credential cho consumer có kiểm soát; không ghi data vào log.
} catch (RuntimeException ex) {
    logger.warn("Vault credential request failed, type={}",
                ex.getClass().getSimpleName());
    throw ex;
} finally {
    metrics.recordVaultLatency(System.nanoTime() - start);
}
~~~

Đoạn minh họa giả định có `logger` và `metrics` do ứng dụng cung cấp. Không log cả exception/message một cách mặc định nếu chưa kiểm tra chúng có chứa nội dung nhạy cảm không. Metric nên chỉ mang service/role và loại kết quả, không đưa username, token hay secret vào label.

**Nguyên tắc coding:** nhận secret sát thời điểm dùng, hạn chế phạm vi biến và bản sao, không trả ra API không bảo vệ, xóa buffer khi API hỗ trợ và không kỳ vọng xóa `String` là bảo đảm xóa mọi bản sao đã tồn tại trong heap.

## 9. Quyền truy cập: ai được yêu cầu loại credential nào?

Vault phân biệt **identity được xác thực** và **policy cấp cho Vault token**. Hai workload có thể đăng nhập bằng cùng loại auth method nhưng không nên có chung policy.

Ví dụ tách quyền theo nhu cầu:

~~~hcl
# orders-kv-reader
path "secret/data/orders/config" {
  capabilities = ["read"]
}

# orders-db-reader
path "database/creds/orders-reader" {
  capabilities = ["read"]
}

# orders-csr-signer
path "pki_int/sign/orders-server" {
  capabilities = ["update"]
}

# orders-transit-encrypter
path "transit/encrypt/orders" {
  capabilities = ["update"]
}
~~~

Các đoạn trên là **ví dụ policy riêng biệt**; chỉ gán đúng policy cho role/workload thực sự cần chức năng đó. Không kết hợp cả bốn chính sách cho mọi Java service. Khi kiểm tra một `403 permission denied`:

- Xác nhận **token hiện tại** đại diện đúng workload; kiểm tra role/auth mount.
- Xác nhận path API thực tế: KV v2 `data/`, PKI `sign/<role>`, Transit `encrypt/<key>`.
- Kiểm tra capability của policy và TTL/token validity; không mở wildcard chỉ để hết `403`.
- Nếu lỗi xảy ra **trước khi có HTTP response**, kiểm tra DNS/TCP/TLS và không chỉnh policy mù.

## 10. Vòng đời cấp phát, thu hồi và xoay credential

~~~mermaid
flowchart LR
    A["Identify workload"] --> B["Authenticate to Vault"]
    B --> C["Issue token/secret/cert"]
    C --> D["Use + audit"]
    D --> E{"Sắp hết hạn / đổi quyền?"}
    E -- "Renewable, vẫn hợp lệ" --> F["Renew"]
    F --> D
    E -- "Không thể renew" --> G["Rotate / reauthenticate"]
    G --> D
    E -- "Workload bị thu hồi" --> H["Revoke + dọn bản sao"]
~~~

### Các tình huống lifecycle cần phân biệt

| Thành phần | Gia hạn/thay thế | Thu hồi |
| --- | --- | --- |
| Vault client token | Renew nếu `renewable` và quyền cho phép; nếu không, login lại theo workload identity. | Revoke token khi không còn nhu cầu/quyền, chú ý token con và lease liên quan. |
| Database dynamic credential | Renew lease khi engine hỗ trợ hoặc nhận credential mới trước hạn. | Revoke lease để Vault thu hồi account/credential theo backend. |
| Static KV password | Xoay tại hệ thống đích và cập nhật Vault bằng quy trình đồng bộ, quản lý version. | Vô hiệu hóa credential cũ ở hệ thống đích; xóa khỏi Vault một mình chưa đủ. |
| PKI certificate/private key | Tạo CSR/key mới, xin cert mới trước `notAfter`, reload runtime. | Thu hồi cert khi hệ sinh thái PKI hỗ trợ CRL/OCSP; bảo vệ/xóa key cũ. |
| Transit key | Chính sách rotate key theo engine; ciphertext cũ có thể cần rewrap. | Thay đổi quyền/khả năng dùng key theo nhu cầu; thao tác hủy key cần kiểm soát vì ảnh hưởng dữ liệu. |

Đặc biệt, **xóa một bản secret khỏi tệp/CI không khiến bản sao đã bị lộ tự mất hiệu lực**. Khi nghi bị lộ token, password hoặc private key, hành động phải bao gồm revoke/rotate tại nguồn xác thực hoặc hệ thống đích.

Với credential động, nếu có pool JDBC hoặc client mTLS giữ kết nối lâu, phải lên kế hoạch thay connection và reload certificate sau rotation. Không chỉ kiểm tra endpoint Vault trả secret mới.

## 11. Giám sát và phản ứng sự cố

Thiết kế quan sát theo **sự kiện và trạng thái**, thay vì xuất giá trị bí mật:

| Cần quan sát | Dữ kiện được phép ghi | Dữ kiện phải tránh |
| --- | --- | --- |
| Vault login | Auth method, role logic, mã HTTP, loại lỗi, độ trễ | JWT login, Vault client token |
| Đọc secret | Engine/path logic đã phê duyệt, success/denied, latency | Value, password, key, full body |
| Lease | TTL, renewal success/fail, lease status đã kiểm soát | Secret payload, thông tin nhạy cảm của account |
| PKI | Role, certificate serial/fingerprint thích hợp, `notAfter`, rotation status | Private key, keystore password |
| TLS | Tên endpoint, CA/cert expiry, handshake status | Private key, session secrets |
| CI/CD | Job ID, policy/role được dùng, pass/fail của secret scan | Environment dump, lệnh có token, artifact chứa key |

Cần cấu hình **Vault audit devices** và hệ thống log/alert theo chính sách tổ chức. Audit log cũng chứa metadata có thể nhạy cảm và có thể bị mất giá trị nếu lưu quá rộng; giới hạn quyền đọc và retention. Nếu chẩn đoán lỗi login, xác định tầng lỗi từ DNS → TCP → TLS → Vault auth → policy → engine; mỗi tầng cần cách khắc phục riêng.

### Quy trình khi phát hiện credential bị lộ

1. Xác định loại credential, nguồn cấp, workload nào sử dụng, phạm vi policy và thời gian hiệu lực.
2. Thu hồi hoặc vô hiệu hóa credential tại **nguồn/quyền kiểm soát phù hợp**: revoke Vault token/lease, rotate DB password, revoke chứng chỉ nếu khả thi và thay private key.
3. Cấp credential mới qua kênh đã chuẩn hóa, cập nhật app/pool/keystore và xác minh consumers chuyển sang bản mới.
4. Loại bỏ bản sao trong source/artifact/log trong phạm vi được phép, xử lý Git history theo quy trình an toàn và quản lý người đã có quyền truy cập.
5. Kiểm tra audit events, điều tra sử dụng trái phép, bổ sung cảnh báo và giảm phạm vi quyền cho lần sau.

Không đưa secret đã lộ vào ticket/chats/log để xin trợ giúp; thay bằng dấu hiệu, hash/fingerprint thích hợp và thông tin không nhạy cảm.

## 12. Kiểm thử tích hợp kiểm soát nguồn cấp

Thiết lập kiểm thử có khả năng phân biệt *lỗi cấp credential*, *lỗi Vault auth*, *lỗi policy* và *lỗi dùng credential*.

| Bài kiểm thử | Kết quả kỳ vọng |
| --- | --- |
| Pod đúng service account và namespace login Vault | Nhận token có đúng policy tối thiểu, dùng được endpoint đã cho. |
| Pod khác namespace/service account thử role đó | Bị từ chối; không có Vault token với quyền của workload hợp lệ. |
| `VaultTemplate` đọc KV v2 đúng path | Lấy được dữ liệu khi được phép, nhưng không log secret. |
| Token thiếu `read` cho `secret/data/orders/config` | KV read trả `403`; không “tự mở quyền” trong ứng dụng. |
| Dynamic DB credential hết hạn hoặc bị revoke | Ứng dụng tái cấp credential/thay connection theo thiết kế, có cảnh báo nếu thất bại. |
| PKI sign CSR từ private key tạo local | Chứng chỉ hợp lệ với key; response không mang private key. |
| Chứng chỉ quá hạn/CA sai/SAN không khớp | TLS handshake thất bại đúng lý do, không tắt verification. |
| Token/secret cố tình đặt trong HTTP payload lỗi | Bộ lọc logging/telemetry không phát tán giá trị nhạy cảm. |
| Xoay cert/key hoặc cập nhật secret file | Consumer thực sự reload và dùng credential mới; không còn dùng bản cũ quá hạn. |
| CI secret scanner chạy trên sample không nhạy cảm | Phát hiện mẫu credential, ngăn commit hoặc artifact không phù hợp. |

Trong unit test, có thể mock `ClientAuthentication`, `VaultTemplate` hoặc lớp adapter nhận credential. Integration test dùng Vault test instance để xác minh path/policy/lifecycle. Để kiểm chứng identity từ cloud hoặc Kubernetes, cần môi trường staging có identity và role thật; mock JWT không chứng minh đã vượt qua cơ chế xác minh chữ ký của Vault.

## 13. Checklist áp dụng cho một Java service

Trước khi đưa ứng dụng Spring Vault vào production, nhóm phát triển và vận hành cần trả lời được:

1. **Nguồn cấp:** JWT/mTLS/token bootstrap đến từ đâu? Ai cấp, ai thu hồi và có tránh được root token/khóa tĩnh không?
2. **Quyền:** Vault auth role ràng buộc chính xác workload nào? Policy giới hạn endpoint KV, Database, Transit, PKI ra sao?
3. **Đường đi:** Credential qua HTTPS có xác minh server? Ai đọc được secret volume, keystore, JVM heap và logs?
4. **Nơi lưu:** Có secret trong Git, image, Dockerfile, CI artifact, ConfigMap, Actuator, telemetry hoặc shell history không?
5. **Khóa riêng:** Key TLS được tạo ở đâu? Có thể dùng CSR signing để tránh chuyển private key không?
6. **TTL/rotation:** Ai renew/revoke Vault token và dynamic lease? JDBC pool hoặc TLS context có reload khi credential đổi không?
7. **Kiểm thử:** Có negative tests cho role, policy, CA, expiration, token leak và rotation không?
8. **Vận hành:** Có audit/alert cho login denied, lease renewal failure, certificate expiry và network/TLS errors không?

**Kết luận:** với Spring Vault, bảo vệ bí mật là quản lý **toàn bộ nguồn cấp và vòng đời** của mật khẩu, token và private key. Workload chứng minh danh tính bằng cơ chế của môi trường; Vault cấp quyền tối thiểu; ứng dụng dùng bí mật đúng phạm vi và trong thời gian cần thiết; hệ thống thu hồi, luân chuyển và giám sát credential liên tục. Nếu làm được các bước này, KV secrets, Transit, PKI và thông tin đăng nhập database có thể được tích hợp qua `VaultTemplate` mà không phụ thuộc vào credential cố định nằm trong mã nguồn.
