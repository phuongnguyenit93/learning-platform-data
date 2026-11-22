# Lưu secret trong vault hoặc secret manager

API thường cần credential để kết nối database, gọi dịch vụ thanh toán, ký webhook, xác minh chữ ký, truy cập object storage hoặc giao tiếp với hệ thống đối tác. Nếu các giá trị này nằm trong source code, file cấu hình được commit, image container, script triển khai hoặc log, chúng có thể bị sao chép và tồn tại lâu hơn dự kiến. Khi một credential bị lộ, attacker có thể dùng quyền của service để đọc dữ liệu, giả mạo request, tạo giao dịch hoặc truy cập hệ thống khác.

Vault hoặc secret manager cung cấp một nơi tập trung để lưu, cấp phát, kiểm soát và theo dõi secret. Ứng dụng xác thực với secret manager bằng danh tính của workload, sau đó chỉ đọc đúng secret mà nó cần. Cách làm này giúp tách credential khỏi mã nguồn và quy trình build, áp dụng quyền truy cập tối thiểu, hỗ trợ rotation/revocation và tạo audit trail.

Secret manager không tự động làm cho secret an toàn. Nếu mọi service đều dùng một root token, policy cho phép đọc toàn bộ path, secret được ghi vào log hoặc ứng dụng tải credential về rồi giữ vô thời hạn, rủi ro vẫn còn. Cần thiết kế toàn bộ vòng đời secret: tạo, lưu, cấp quyền, phân phối, sử dụng, xoay vòng, thu hồi, kiểm toán và xóa.

## 1. Secret là gì và vì sao cần secret manager?

Secret là dữ liệu có khả năng cấp quyền, xác thực danh tính hoặc bảo vệ tính bí mật/toàn vẹn của hệ thống. Ví dụ:

- API key hoặc client secret để gọi API đối tác.
- Database username/password hoặc credential cấp phát động.
- Private key dùng ký JWT, request hoặc webhook.
- Secret dùng xác minh chữ ký webhook từ provider.
- Credential truy cập message broker, cache, object storage hoặc SMTP.
- Token dịch vụ có quyền truy cập vào một hệ thống khác.
- Key encryption hoặc key wrapping theo kiến trúc quản lý khóa.

Không phải mọi cấu hình đều là secret. Base URL, timeout, page size hoặc tên feature flag thường là cấu hình thông thường, dù vẫn có thể nhạy cảm trong một số môi trường. Phân loại đúng giúp tránh đưa toàn bộ config vào secret manager và giảm quyền truy cập không cần thiết.

| Loại dữ liệu | Ví dụ | Nơi quản lý phù hợp |
|---|---|---|
| Cấu hình thông thường | Timeout, page size, public endpoint | Config service hoặc cấu hình triển khai |
| Secret tĩnh | API key, client secret, webhook signing secret | Vault/secret manager |
| Secret động | Database credential có lease ngắn | Secret engine hoặc broker cấp credential |
| Key mã hóa/ký | Private signing key, key encryption | KMS/HSM hoặc secret manager có tích hợp key service |
| Public key/certificate công khai | JWKS public key, CA certificate | Config/artifact được quản lý; vẫn cần kiểm soát integrity |
| Credential của người dùng | Access token/session token cá nhân | Session/token store theo thiết kế identity; không gom tùy tiện vào secret manager của workload |

### 1.1. Rủi ro khi lưu secret trong code hoặc config

Secret có thể bị lộ qua nhiều đường:

- Git history vẫn giữ giá trị dù commit mới đã xóa dòng secret.
- Pull request, code review, fork hoặc bản sao repository chứa credential.
- Docker image/layer và build artifact giữ file cấu hình cũ.
- Environment dump, crash dump, debug endpoint hoặc diagnostic bundle.
- Shell history, command-line argument và process listing.
- Log, trace, exception hoặc HTTP client debug output.
- Backup, file tạm, workspace CI/CD và cache build.
- Credential dùng chung khiến không thể xác định service nào đã sử dụng.

Xóa secret khỏi file hiện tại chưa đủ nếu giá trị đã từng bị commit hoặc phân phối. Khi có dấu hiệu lộ secret, cần thu hồi/rotate credential và điều tra phạm vi sử dụng, đồng thời dọn các bản sao theo quy trình phù hợp.

## 2. Vault và secret manager hoạt động như thế nào?

Vault/secret manager là một dịch vụ bảo vệ secret, thường cung cấp API để ứng dụng hoặc operator:

1. Xác thực danh tính.
2. Được policy cho phép truy cập một secret path hoặc một loại secret engine.
3. Đọc secret tĩnh hoặc yêu cầu cấp credential động.
4. Nhận secret cùng metadata như version, lease hoặc thời hạn.
5. Gia hạn hoặc thu hồi lease nếu loại secret hỗ trợ.
6. Ghi audit event cho các thao tác quan trọng.

Một secret manager có thể là dịch vụ do cloud provider vận hành, một hệ thống Vault tự quản lý hoặc một nền tảng quản lý secret tương đương. Dù chọn sản phẩm nào, các yêu cầu cốt lõi vẫn gồm identity, authorization, encryption, audit, rotation, availability và recovery.

### 2.1. Kiến trúc tham khảo

~~~mermaid
flowchart TD
    A[API workload] -->|Workload identity| B[Authentication]
    B --> C[Secret manager policy]
    C -->|Least privilege| D[Secret path or engine]
    D --> E[Encrypted secret storage]
    D --> F[Dynamic credential issuer]
    E --> G[Short-lived secret response]
    F --> G
    G --> H[Application memory or protected file]
    H --> I[Partner API / Database]
    J[Audit device] --> K[Protected audit sink]
    B --> J
    C --> J
    D --> J
    L[KMS / HSM] --> E
~~~

Ứng dụng chỉ nên nhận secret mà identity của nó được phép đọc. Secret manager chịu trách nhiệm xác thực caller, đánh giá policy và ghi audit; KMS/HSM có thể bảo vệ encryption key hoặc thực hiện thao tác ký/mã hóa mà không xuất private key.

### 2.2. Vault không phải database cấu hình dùng chung

Không nên xem Vault như một kho key/value mà mọi service đều được đọc. Secret manager là một security boundary có quyền rất mạnh. Cần:

- Tách secret theo service, môi trường và mục đích.
- Định nghĩa policy theo path/action cụ thể.
- Tách quyền đọc secret khỏi quyền tạo, sửa, xóa và quản trị.
- Dùng identity riêng cho từng workload.
- Giới hạn network access đến endpoint secret manager.
- Bảo vệ audit log và backup.
- Có quy trình break-glass và thu hồi quyền quản trị.

## 3. Thiết kế cấu trúc lưu trữ secret

Trước khi chọn path, cần có quy ước tên và phân cấp. Một cấu trúc ví dụ:

~~~text
secret/
  dev/
    payments-api/
      partner-client
  staging/
    payments-api/
      partner-client
  prod/
    payments-api/
      partner-client
  prod/
    notification-api/
      smtp-client
~~~

Đây là ví dụ logic. Với KV version 2 của Vault, đường dẫn API đọc/ghi có thành phần data/metadata riêng; policy phải dùng đúng path tương ứng. Không sao chép tên path mẫu mà chưa xác nhận secret engine và mount path đang triển khai.

### 3.1. Tách theo môi trường

Development, staging và production cần secret riêng:

- Không dùng API key production trong laptop developer.
- Không dùng chung database password giữa staging và production.
- Không cho workload staging đọc path production.
- Không dùng một token CI có thể truy cập tất cả môi trường.
- Dùng credential sandbox cho provider ở môi trường test.

Việc tách có thể thực hiện bằng namespace, mount, path, project/account hoặc vault instance riêng tùy nền tảng. Mục tiêu là tạo ranh giới quyền thực sự, không chỉ thêm chữ prod vào tên một biến.

### 3.2. Tách theo service và chức năng

Mỗi service chỉ nên đọc secret phục vụ chức năng của nó. Ví dụ payments-api có thể cần credential gọi payment provider và database credential của chính service. Nó không cần đọc signing key của identity service hoặc SMTP password của notification service.

Nếu một service có nhiều tích hợp, cân nhắc tách identity hoặc policy theo từng workload/connector để giới hạn tác động khi một thành phần bị xâm nhập. Không cấp một policy wildcard như secret/data/prod/* chỉ để giảm công sức cấu hình.

### 3.3. Tách theo tenant khi cần

Một số hệ thống tích hợp với credential riêng cho từng merchant hoặc tenant. Có thể tổ chức path theo tenant, nhưng không để client tự chọn path hoặc tenant ID để đọc secret.

Ứng dụng cần:

1. Xác thực caller và xác định tenant từ security context đã xác minh.
2. Kiểm tra caller có quyền sử dụng tích hợp của tenant.
3. Resolve secret reference từ mapping nội bộ được quản lý.
4. Đọc secret bằng workload identity có phạm vi phù hợp.
5. Không trả secret về client; chỉ dùng server-side cho outbound call.

Nếu có số lượng tenant lớn, nên cân nhắc secret broker/service chuyên dụng thay vì cấp cho API workload quyền đọc toàn bộ path tenant. Mọi lựa chọn phải giới hạn khả năng một bug IDOR khiến service đọc credential của tenant khác.

## 4. Xác thực với secret manager bằng workload identity

Ứng dụng cần chứng minh danh tính của chính nó khi gọi secret manager. Không nhúng root token, admin token hoặc token dùng chung vào image/container để tất cả instance sử dụng.

Các cơ chế thường gặp:

| Môi trường chạy | Identity có thể dùng |
|---|---|
| Kubernetes | Kubernetes ServiceAccount token được xác minh bởi auth method của Vault hoặc cloud workload identity |
| Cloud VM | Instance identity/IAM role hoặc machine identity |
| Serverless | Execution role hoặc workload identity do nền tảng cấp |
| CI/CD | OIDC federation hoặc identity ngắn hạn gắn với pipeline/repository/environment |
| Datacenter/VM truyền thống | AppRole với SecretID được phân phối và bảo vệ cẩn thận, hoặc machine certificate |
| Developer workstation | SSO/user identity có quyền dev riêng và thời hạn ngắn |

### 4.1. Least privilege cho workload

Mỗi workload identity cần:

- Chỉ được xác thực vào role tương ứng.
- Chỉ đọc các path/secret engine cần thiết.
- Không có quyền list toàn bộ secret nếu không cần.
- Không có quyền write/delete/admin.
- Có audience, namespace, service account hoặc attribute binding phù hợp.
- Có TTL và khả năng thu hồi.
- Được tách theo môi trường và service.

Với Kubernetes auth, role nên ràng buộc service account name và namespace cụ thể. Nếu chỉ kiểm tra namespace chung hoặc chấp nhận mọi service account, một pod khác trong cùng cluster có thể mượn danh tính để đọc secret.

### 4.2. AppRole và SecretID

AppRole có thể phù hợp cho workload không có identity federation thuận tiện. Tuy nhiên, SecretID cũng là credential nhạy cảm. Cần:

- Dùng SecretID response-wrapping hoặc cơ chế phân phối một lần nếu nền tảng hỗ trợ.
- Đặt TTL và số lần sử dụng tối đa.
- Không đưa SecretID vào source code, image hoặc command line.
- Hạn chế nơi có thể đọc file bootstrap.
- Xoay vòng/revoke khi nghi ngờ bị lộ.
- Không dùng role có policy quản trị.

Không lưu AppRole RoleID/SecretID cố định trong repository rồi coi đó là giải pháp thay thế cho workload identity.

### 4.3. Token secret manager

Sau khi xác thực, ứng dụng có thể nhận token ngắn hạn để gọi API secret manager. Token này cũng là secret:

- Không ghi vào log hoặc trace.
- Không trả cho client.
- Không lưu trong file có quyền đọc rộng.
- Dùng token sink/agent hoặc SDK được quản lý phù hợp.
- Giới hạn TTL, policy và khả năng renew.
- Thu hồi khi workload kết thúc hoặc bị xâm nhập.

Không dùng root token cho ứng dụng. Root token chỉ dành cho thao tác bootstrap/khẩn cấp theo quy trình được kiểm soát, không dùng trong runtime thông thường.

## 5. Policy và phân quyền truy cập secret

Policy cần thể hiện rõ workload được phép làm gì trên secret path hoặc secret engine. Quyền đọc, ghi, xóa, liệt kê và quản trị là các quyền khác nhau.

Ví dụ policy HCL cho Vault KV v2, chỉ cho payments-api đọc một secret cụ thể:

~~~hcl
path "secret/data/prod/payments-api/partner-client" {
  capabilities = ["read"]
}
~~~

Đây là ví dụ policy cho mount tên secret với KV v2. Nếu mount path, namespace hoặc engine khác, phải điều chỉnh path. Ứng dụng không cần quyền create, update, delete, list hoặc sudo chỉ để đọc credential.

### 5.1. Phân biệt quyền đọc và quyền quản trị

| Vai trò | Quyền phù hợp |
|---|---|
| Runtime workload | Đọc secret cụ thể hoặc lấy credential động được cấp |
| Secret operator | Tạo/cập nhật secret trong phạm vi phụ trách |
| Security administrator | Quản lý policy/auth method theo change control |
| Auditor | Đọc audit metadata theo quyền, không cần đọc secret value |
| CI/CD deployer | Thường chỉ cần kích hoạt workload/deployment; tránh quyền đọc secret production trực tiếp |
| Break-glass operator | Quyền khẩn cấp có thời hạn, approval và audit tăng cường |

Tách người tạo secret khỏi người dùng secret nếu quy trình yêu cầu separation of duties. Người có quyền sửa policy hoặc cấp identity có thể gián tiếp đọc secret, vì vậy quyền quản trị control plane cần được xem là quyền đặc biệt.

### 5.2. Tránh wildcard và quyền list

Quyền list có thể làm lộ tên secret, tên service, tenant hoặc cấu trúc hệ thống ngay cả khi caller không đọc được value. Cấp quyền path chính xác thay vì wildcard rộng. Nếu ứng dụng cần biết một secret reference, cung cấp reference qua config đã kiểm soát; không cấp quyền duyệt toàn bộ kho.

### 5.3. Kiểm tra policy bằng negative test

Không chỉ kiểm tra service đọc được secret mong muốn. Cần chứng minh nó không thể:

- Đọc secret của service khác.
- Đọc path production từ identity staging.
- List mount hoặc tenant path không liên quan.
- Ghi đè hoặc xóa credential.
- Đọc secret quản trị hoặc root token.
- Dùng token của workload khác.

## 6. Lưu trữ và mã hóa secret

Secret manager thường mã hóa dữ liệu khi lưu và bảo vệ kênh truyền bằng TLS. Cần xác định mô hình key management thay vì chỉ kiểm tra một checkbox encryption.

### 6.1. Encryption in transit

- Ứng dụng gọi secret manager qua TLS.
- Xác minh certificate chain và hostname.
- Không tắt certificate validation để xử lý lỗi môi trường.
- Dùng private network, private endpoint hoặc network policy khi phù hợp.
- Có thể dùng mTLS/workload identity cho kết nối service-to-service.
- Không cho phép downgrade sang HTTP.

### 6.2. Encryption at rest và envelope encryption

Một mô hình phổ biến là mã hóa dữ liệu bằng data encryption key (DEK), sau đó mã hóa DEK bằng key encryption key (KEK) được quản lý bởi KMS/HSM. Secret manager lưu ciphertext và metadata; KEK có thể được bảo vệ, rotation hoặc kiểm soát bằng dịch vụ quản lý khóa.

~~~mermaid
flowchart TD
    S[Secret plaintext] --> D[Encrypt with DEK]
    D --> C[Ciphertext]
    K[KEK in KMS/HSM] --> W[Wrap DEK]
    W --> E[Encrypted DEK]
    C --> R[Stored record]
    E --> R
    R --> U[Authorized read]
    U --> X[Unwrap DEK through KMS]
    X --> P[Decrypt in trusted service]
~~~

Đây là mô hình khái niệm. Cách triển khai cụ thể phụ thuộc secret manager và KMS. Không tự viết thuật toán mã hóa hoặc lưu KEK cạnh ciphertext. Quyền gọi KMS, quyền giải mã và quyền đọc secret cần được tách theo yêu cầu.

### 6.3. Phân biệt secret storage và cryptographic key management

API key hoặc client secret thường cần được ứng dụng đọc để đặt vào outbound request. Private signing key có thể không cần xuất khỏi KMS/HSM; ứng dụng gửi dữ liệu cần ký đến dịch vụ ký và nhận chữ ký. Cách thứ hai giảm số nơi có thể lấy private key.

Vault có thể cung cấp transit engine hoặc tích hợp KMS/HSM để thực hiện thao tác crypto. Hãy chọn cơ chế dựa trên yêu cầu:

- Nếu ứng dụng cần secret dạng text/credential, dùng secret engine phù hợp.
- Nếu ứng dụng cần ký/mã hóa nhưng không cần biết key bytes, ưu tiên cryptographic service.
- Nếu key cần compliance/HSM, xác minh vị trí, quyền và audit của key operation.
- Nếu key export là bắt buộc, giới hạn workload, memory exposure và rotation.

### 6.4. Backup cũng chứa secret

Backup, snapshot và replica của secret manager cần được mã hóa, kiểm soát quyền và có retention. Không để bản backup được lưu trong bucket công khai hoặc tài khoản cloud có quyền rộng. Kiểm thử restore cần có kiểm soát để không vô tình khôi phục secret đã bị thu hồi vào môi trường đang hoạt động.

## 7. Secret tĩnh và secret động

Secret manager thường hỗ trợ hai cách cấp secret.

### 7.1. Secret tĩnh

Secret tĩnh được tạo bên ngoài hoặc do operator quản lý rồi lưu trong secret store. Ví dụ API key do payment provider cấp hoặc webhook signing secret.

Đặc điểm:

- Giá trị thường tồn tại cho đến khi rotate/revoke.
- Ứng dụng cần đọc version hiện hành.
- Cần kế hoạch overlap để chuyển credential.
- Có thể lưu metadata owner, provider, environment và ngày hết hạn.

Secret tĩnh dễ triển khai nhưng nếu tồn tại lâu, attacker có nhiều thời gian sử dụng sau khi bị lộ. Cần rotation định kỳ hoặc theo sự kiện, theo khả năng của provider.

### 7.2. Secret động

Secret động được secret manager hoặc secret engine cấp khi workload yêu cầu, thường có lease/TTL. Ví dụ database engine tạo username/password riêng cho mỗi service hoặc mỗi instance.

Ưu điểm:

- Credential có thời hạn ngắn.
- Có thể thu hồi theo lease.
- Giảm dùng chung password dài hạn.
- Có thể gắn identity và audit với yêu cầu cấp phát.

Ứng dụng cần xử lý lease expiry, renew và revoke. Không giả định mọi dynamic credential tự động được gia hạn hoặc thu hồi đúng khi process crash. Cần theo dõi lease và dọn credential hết hạn ở hệ thống đích.

### 7.3. Chọn secret tĩnh hay động

| Nhu cầu | Hướng phù hợp |
|---|---|
| Provider chỉ cấp một API key dài hạn | Secret tĩnh trong manager, rotation theo provider |
| Database hỗ trợ tạo user/credential ngắn hạn | Dynamic secret engine |
| Ký JWT bằng private key cần bảo vệ cao | KMS/HSM hoặc signing service |
| Webhook provider có secret cố định | Secret tĩnh có version và overlap rotation |
| Service-to-service trong cloud hỗ trợ identity federation | Workload identity có thể loại bỏ nhu cầu lưu password tĩnh |

Ưu tiên bỏ credential dài hạn nếu hệ thống đích hỗ trợ workload identity hoặc short-lived token an toàn. Secret manager không nên trở thành lý do để tiếp tục dùng password dài hạn khi có cơ chế identity tốt hơn.

## 8. Phân phối secret đến ứng dụng

Có nhiều cách để workload lấy secret. Chọn cách phù hợp với runtime, khả năng reload và threat model.

### 8.1. Runtime API retrieval

Ứng dụng xác thực với secret manager rồi đọc secret qua SDK/API khi khởi động hoặc khi cần. Ưu điểm là policy được kiểm tra tại thời điểm đọc và có thể lấy version mới. Nhược điểm là ứng dụng phụ thuộc availability của secret manager và phải quản lý token/cache.

Nên:

- Đọc đúng path đã cấu hình, không lấy path từ client.
- Giới hạn secret trong memory và không log object response.
- Cache có TTL phù hợp, không cache vô thời hạn.
- Có timeout/retry hợp lý cho secret manager.
- Theo dõi version và thời điểm refresh.
- Không để mỗi request API đều gọi secret manager nếu có thể dùng cache an toàn.

### 8.2. Agent hoặc sidecar ghi file

Vault Agent hoặc secret manager agent có thể xác thực workload, lấy secret và render vào file có quyền truy cập hạn chế. Ứng dụng đọc file trong runtime.

Kiểm soát:

- File nằm trong filesystem riêng hoặc memory-backed volume khi phù hợp.
- Owner/group và permission chỉ cho process cần đọc.
- Không mount file vào container không liên quan.
- Không đưa secret vào image layer.
- File update phải atomic để ứng dụng không đọc file nửa chừng.
- Theo dõi template/render error và thời điểm refresh.
- Xóa file tạm khi workload kết thúc theo khả năng nền tảng.

File injection có thể giúp ứng dụng không phải tự quản lý token secret manager. Tuy nhiên, process có quyền đọc file vẫn có thể lấy secret; cần giới hạn quyền trong container/pod.

### 8.3. Environment variable

Truyền secret qua environment variable tiện nhưng có rủi ro:

- Có thể xuất hiện trong process inspection hoặc diagnostic output.
- Có thể bị ghi vào crash dump hoặc log cấu hình.
- Thường khó cập nhật khi process đang chạy.
- Có thể bị kế thừa bởi subprocess.
- Nhiều nền tảng hiển thị env trong giao diện quản trị hoặc debug.

Chỉ dùng khi nền tảng có cơ chế bảo vệ phù hợp và đã đánh giá threat model. Không mặc định env var an toàn chỉ vì được inject lúc deploy. Với secret cần rotation runtime, file/agent hoặc API retrieval có thể phù hợp hơn.

### 8.4. Không truyền secret qua command line

Tránh đặt secret trong command argument, shell command hoặc URL. Các giá trị này có thể xuất hiện trong shell history, process list, audit của CI/CD hoặc proxy log. Dùng SDK, file được bảo vệ, standard input có kiểm soát hoặc cơ chế identity của nền tảng.

## 9. Ứng dụng dùng secret để gọi API đối tác

Secret manager thường cung cấp API key hoặc client secret cho outbound integration. Ứng dụng vẫn cần bảo vệ credential khi sử dụng:

1. Xác thực caller của API nội bộ.
2. Kiểm tra function/object authorization trước khi thực hiện nghiệp vụ.
3. Xác định provider/account từ cấu hình tin cậy.
4. Lấy credential bằng workload identity và policy tối thiểu.
5. Gửi credential qua header theo contract của provider trên TLS.
6. Không đưa credential vào URL hoặc response cho client.
7. Redact Authorization header và payload nhạy cảm khỏi log/trace.
8. Theo dõi version, expiry và lỗi xác thực upstream.

Secret manager chỉ giải quyết việc lưu và cấp credential. Nó không xác minh response của provider, không chống SSRF và không thay thế validation hoặc authorization của API nội bộ.

### 9.1. Tách credential theo provider và operation

Nếu một provider có API key chỉ đọc và key có quyền hoàn tiền, không nên dùng một credential quyền rộng cho mọi request. Tạo credential riêng theo môi trường và chức năng nếu provider hỗ trợ. Giới hạn IP/source, audience, scope hoặc endpoint ở phía provider khi có thể.

### 9.2. Webhook signing secret

Webhook secret dùng để xác minh signature inbound cần được đọc bởi thành phần verification phù hợp. Không phân phối secret này cho mọi worker nếu worker chỉ cần nhận một verified event envelope. Giữ raw payload/hash và verification metadata theo thiết kế; giảm số workload có thể đọc secret gốc.

## 10. Rotation và versioning

Rotation thay credential hiện tại bằng credential mới để giảm thời gian sử dụng và giới hạn tác động nếu secret cũ bị lộ. Rotation phải phối hợp giữa secret manager, ứng dụng và hệ thống cấp credential.

Quy trình tham khảo cho API key của provider:

1. Tạo credential mới ở provider trong khi credential cũ vẫn còn hiệu lực.
2. Lưu version mới vào secret manager với metadata và owner.
3. Cấp quyền đọc version mới cho workload phù hợp.
4. Cập nhật ứng dụng hoặc agent để nạp version mới.
5. Xác minh outbound call hoạt động bằng credential mới.
6. Theo dõi lỗi xác thực và bảo đảm mọi instance đã chuyển.
7. Thu hồi credential cũ ở provider.
8. Ghi audit và xác nhận version cũ không còn được sử dụng.

Nếu provider chỉ cho phép một key hoạt động tại một thời điểm, cần maintenance window hoặc cơ chế chuyển đổi khác. Không giả định mọi provider hỗ trợ overlap.

### 10.1. Rotation không gián đoạn

Với credential có overlap:

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant P as Provider
    participant V as Secret Manager
    participant A as API Workload
    O->>P: Create new credential
    P-->>O: New credential
    O->>V: Store new secret version
    A->>V: Read current approved version
    V-->>A: New credential
    A->>P: Test outbound request
    P-->>A: Success
    O->>P: Revoke old credential
    O->>V: Retire old version per policy
~~~

Trong thực tế, có thể cần triển khai theo canary, chờ cache TTL, xác nhận toàn bộ region và giữ rollback window. Không xóa version cũ khỏi secret manager trước khi xác nhận mọi instance đã chuyển, nhưng cũng không giữ vô thời hạn.

### 10.2. Versioning và rollback

Version giúp truy vết và khôi phục khi secret mới bị cấu hình sai. Tuy nhiên, rollback về secret cũ chỉ an toàn nếu credential đó vẫn hợp lệ và chưa bị thu hồi vì compromise. Nếu secret cũ bị lộ, không rollback chỉ để khôi phục availability; cần cấp credential mới hoặc chuyển degraded mode.

Không log secret value khi ghi version. Audit nên ghi path, version, actor, thời điểm và change reference.

## 11. Lease, renewal và revocation

Dynamic secret thường đi kèm lease. Lease có thời hạn và có thể được renew hoặc revoke.

Ứng dụng cần:

- Theo dõi TTL và thời điểm hết hạn.
- Renew trước expiry với jitter để tránh nhiều instance cùng gọi.
- Xử lý renew failure và credential đã hết hạn.
- Dừng sử dụng credential khi lease bị revoke.
- Thu hồi lease khi workload kết thúc nếu có thể.
- Không giả định restart process sẽ tự động thu hồi credential cũ.
- Có reconciliation để tìm credential/lease mồ côi.

### 11.1. Xử lý khi renewal thất bại

Nếu credential hiện tại còn hiệu lực, ứng dụng có thể tiếp tục dùng trong một khoảng thời gian có giới hạn theo policy và retry renew. Khi credential hết hạn hoặc bị revoke, request mới phụ thuộc credential đó phải thất bại an toàn. Không chuyển sang password hard-coded hoặc credential của môi trường khác.

Với thao tác tài chính hoặc thay đổi quyền, có thể cần từ chối action khi không xác định được credential còn hợp lệ. Với thao tác đọc ít rủi ro, có thể tiếp tục trong thời gian ngắn nếu secret hiện tại vẫn được xác minh còn hiệu lực. Quyết định cần theo từng tích hợp.

### 11.2. Revocation khi compromise

Khi secret bị lộ:

1. Xác định secret path, version, provider và workload được cấp quyền.
2. Thu hồi credential ở hệ thống đích trước hoặc đồng thời theo kế hoạch.
3. Revoke token/lease của secret manager liên quan.
4. Cấp credential mới và cập nhật workload.
5. Tìm kiếm log/audit về lần đọc và sử dụng đáng ngờ.
6. Kiểm tra Git history, image, artifact, CI/CD, backup và log để xác định phạm vi.
7. Xác minh credential cũ không còn hoạt động.
8. Ghi incident và điều chỉnh policy/rotation.

Chỉ xóa secret khỏi Vault không làm credential cũ mất hiệu lực ở provider. Thu hồi tại hệ thống đích là bước quan trọng.

## 12. Availability, HA và disaster recovery của secret manager

Nếu secret manager ngừng hoạt động, workload mới có thể không lấy được credential và workload đang chạy có thể không renew được lease. Secret manager vì vậy là dependency quan trọng của API.

Thiết kế cần xem xét:

- HA cluster hoặc dịch vụ managed có SLA phù hợp.
- TLS certificate và DNS endpoint dự phòng.
- Quorum/seal/unseal hoặc cơ chế key recovery theo sản phẩm.
- Backup được mã hóa, quyền truy cập và retention.
- Snapshot/replication và consistency của secret version.
- Audit sink độc lập hoặc buffer bền vững.
- Kế hoạch phục hồi KMS/HSM và quyền giải mã.
- Kiểm thử restore định kỳ.

### 12.1. Cache và degraded mode

Ứng dụng có thể giữ credential hiện hành trong memory hoặc file được bảo vệ để không cần gọi secret manager cho mỗi request. Nhưng cache cần:

- TTL và maximum staleness rõ ràng.
- Không ghi secret vào disk/log ngoài thiết kế.
- Theo dõi version và expiry.
- Có cách nhận biết secret đã bị revoke.
- Không dùng cache của environment hoặc tenant khác.
- Không tiếp tục vô hạn khi secret manager không khả dụng.

Với secret tĩnh chưa hết hạn và chưa bị revoke, có thể cho phép workload tiếp tục trong một thời gian ngắn đã định. Với dynamic secret đã hết lease, không tiếp tục sử dụng. Với secret nghi ngờ bị compromise, cache không được giữ credential cũ chỉ để duy trì availability.

### 12.2. Seal/unseal và recovery key

Một số Vault deployment có cơ chế seal/unseal và recovery key. Các key này có quyền rất mạnh, cần lưu trữ tách biệt, phân chia trách nhiệm và bảo vệ offline hoặc trong KMS/HSM theo kiến trúc. Không lưu recovery key trong cùng cluster hoặc repository mà nó có thể mở khóa.

Runbook recovery cần quy định ai được tham gia, cách xác minh operator, thứ tự khôi phục KMS/Vault, cách kiểm tra audit và cách xác nhận secret không bị rollback về version đã thu hồi.

## 13. Audit, monitoring và phát hiện bất thường

Secret manager nên ghi audit cho các thao tác xác thực, đọc, tạo, sửa, xóa, đổi policy, renew/revoke lease và thao tác quản trị. Audit log cần được bảo vệ khỏi sửa/xóa bởi workload thông thường.

Theo dõi:

- Identity/workload nào đọc path nào.
- Secret path/version được truy cập và thời điểm.
- Request bị deny do policy.
- Số lần đọc bất thường hoặc đọc nhiều path.
- Token issuance, renewal, revoke và expiry.
- Secret version thay đổi ngoài change window.
- Policy/auth method/role thay đổi.
- Lease còn tồn tại sau khi workload kết thúc.
- Audit sink không ghi được hoặc log bị gián đoạn.
- Secret manager latency, availability và KMS/HSM error.

Không ghi secret value vào audit. Audit cần ghi metadata đủ để điều tra nhưng không làm lộ credential.

### 13.1. Alert hữu ích

- Một service đọc secret path của service khác.
- Workload staging thử đọc secret production.
- Identity mới đột ngột đọc nhiều secret.
- Root/admin token được dùng trong runtime.
- Policy wildcard mới được thêm.
- Secret được đọc từ region hoặc network bất thường.
- Credential sắp hết hạn hoặc rotation không hoàn tất.
- Dynamic lease tăng bất thường hoặc không được revoke.
- Audit logging bị disable hoặc không ghi được.

### 13.2. Correlation với API request

Khi một API request gọi provider, có thể ghi trace/correlation ID cùng provider name, workload identity và secret version reference (không phải secret value). Điều này giúp điều tra request nào dùng version nào mà không tiết lộ credential. Tránh đặt secret path chứa tenant PII hoặc credential trong metric label có cardinality cao.

## 14. Tích hợp secret manager vào ứng dụng Java/Spring

Ứng dụng nên phụ thuộc vào một abstraction lấy secret thay vì rải lệnh gọi Vault khắp service. Điều này giúp kiểm thử, thay nhà cung cấp và kiểm soát cache/rotation tập trung.

### 14.1. Interface lấy secret

~~~java
public interface SecretProvider {
    SecretValue read(String secretReference);
}

public record SecretValue(
    String value,
    String version,
    Instant expiresAt
) {
    @Override
    public String toString() {
        return "SecretValue[version=" + version
            + ", expiresAt=" + expiresAt + "]";
    }
}
~~~

Trong production, implementation dùng SDK/agent được cấu hình bằng workload identity. Trong test, có thể dùng implementation giả với secret test. Ví dụ ghi đè toString để tránh record tự sinh chuỗi chứa secret value; không đưa value vào exception message, log hoặc trace. String trong Java là immutable và không thể xóa nội dung chắc chắn khỏi heap, vì vậy cần giới hạn số bản sao và thời gian giữ secret trong memory.

### 14.2. Dùng secret ở outbound client

~~~java
public PartnerClient createPartnerClient(
        SecretProvider secretProvider,
        PartnerConfig config) {

    SecretValue apiKey = secretProvider.read(
        config.apiKeyReference());

    return PartnerClient.builder()
        .baseUrl(config.baseUrl())
        .apiKey(apiKey.value())
        .connectTimeout(config.connectTimeout())
        .build();
}
~~~

Đây là ví dụ rút gọn. Trong ứng dụng thật, cần tránh tạo client mới cho mọi request, có cơ chế refresh client khi secret version thay đổi và không log cấu hình chứa apiKey. Base URL phải đến từ config được quản lý/allowlist; secret manager không phải nơi để lấy URL tùy ý do client gửi.

### 14.3. Cấu hình Spring Cloud Vault ở mức khái niệm

Một cấu hình có thể khai báo URI Vault, auth method, role và secret backend bằng cơ chế Config Data hoặc integration tương ứng với phiên bản Spring Cloud Vault đang dùng. Ví dụ minh họa:

~~~yaml
spring:
  cloud:
    vault:
      uri: https://vault.internal.example
      authentication: KUBERNETES
      kubernetes:
        role: payments-api
      kv:
        enabled: true
        backend: secret
        default-context: prod/payments-api
~~~

Đây chỉ là cấu hình minh họa; tên property và cách bật Config Data phụ thuộc phiên bản Spring Boot/Spring Cloud Vault. Trong production, URI phải dùng TLS và hostname verification; không đặt Vault token hoặc secret value trong file YAML. Role Kubernetes phải ràng buộc service account và namespace đúng. Không dùng cấu hình dev token/root token cho production.

### 14.4. Kiểm thử ứng dụng

Kiểm thử:

- Không có secret reference thì ứng dụng fail startup hoặc không bật integration theo policy đã định.
- Secret manager timeout không làm ứng dụng chuyển sang hard-coded credential.
- Workload identity không đọc được path ngoài policy.
- Secret rotation được nhận và client chuyển version đúng.
- Secret hết hạn/revoked làm outbound request thất bại an toàn.
- Exception/log không chứa secret value hoặc token.
- Test dùng secret giả và không gọi provider production.

## 15. Quản lý secret trong CI/CD và developer workflow

CI/CD thường cần credential để deploy hoặc chạy integration test. Đây là một nguồn rò rỉ phổ biến vì pipeline có thể chạy code do pull request hoặc dependency không tin cậy cung cấp.

Nguyên tắc:

- Dùng OIDC/workload federation để đổi identity pipeline lấy token ngắn hạn.
- Tách quyền pipeline build, test và deploy production.
- Không cấp production secret cho job chạy từ fork hoặc pull request không tin cậy.
- Mask secret trong log nhưng không coi masking là bảo vệ đầy đủ.
- Không truyền secret qua command line hoặc artifact.
- Hạn chế secret exposure trong job step cần dùng.
- Thu hồi identity/credential sau job hoặc theo TTL.
- Audit ai/commit/workflow/environment đã yêu cầu secret.

Developer workstation nên dùng SSO và quyền dev riêng. Không tải secret production về laptop chỉ để debug nếu không có phê duyệt và biện pháp bảo vệ dữ liệu phù hợp.

## 16. Những sai lầm thường gặp

- **Dùng root token trong ứng dụng:** một lỗ hổng application có thể chiếm toàn bộ secret manager.
- **Dùng chung một token cho nhiều service:** khó giới hạn và truy vết khi compromise.
- **Policy wildcard:** một service đọc được secret ngoài phạm vi.
- **Lưu secret trong Git rồi xóa ở commit sau:** Git history và artifact vẫn có thể giữ credential.
- **Đưa secret vào image/container layer:** secret tồn tại trong mọi bản sao image.
- **Truyền secret qua command line/URL:** dễ lộ qua history, process list hoặc log.
- **Dùng environment variable không đánh giá rủi ro:** secret có thể xuất hiện trong dump và subprocess.
- **Không rotation:** credential dài hạn tiếp tục có giá trị sau khi bị lộ.
- **Xóa secret khỏi Vault nhưng quên revoke ở provider:** credential cũ vẫn dùng được.
- **Không quản lý lease:** dynamic credential tồn tại quá hạn hoặc bị bỏ quên.
- **Cache vô thời hạn:** workload tiếp tục dùng secret cũ sau khi revoke.
- **Dùng một secret cho mọi tenant:** sự cố một tenant ảnh hưởng các tenant khác.
- **Cho phép ứng dụng tự chọn secret path:** có thể tạo đường đọc credential chéo tenant.
- **Log response của secret manager:** token hoặc secret value bị ghi ra log.
- **Không bảo vệ backup/audit:** bản sao và bằng chứng trở thành điểm rò rỉ.
- **Không kiểm thử restore/rotation:** chỉ phát hiện vấn đề khi có sự cố thật.

## 17. Checklist trước khi phát hành

- [ ] Secret được phân loại riêng với cấu hình thông thường và dữ liệu người dùng.
- [ ] Secret không nằm trong source code, Git history, image, artifact hoặc file cấu hình công khai.
- [ ] Có inventory cho secret: owner, service, môi trường, provider, purpose và expiry.
- [ ] Mỗi workload có identity riêng; không dùng root/admin token trong runtime.
- [ ] Auth method ràng buộc đúng workload, namespace, audience hoặc environment.
- [ ] Policy chỉ cấp quyền cần thiết trên path/engine cụ thể.
- [ ] Quyền read/write/delete/list/admin được tách biệt.
- [ ] Secret production không thể được đọc từ workload staging/dev.
- [ ] Tenant mapping được xác minh trước khi resolve secret reference.
- [ ] Kết nối secret manager dùng TLS, hostname verification và network policy phù hợp.
- [ ] Encryption at rest, KMS/HSM và backup được bảo vệ theo threat model.
- [ ] Secret tĩnh có version và rotation plan; secret động có lease/renew/revoke.
- [ ] Ứng dụng không đưa secret vào URL, command line, log hoặc response cho client.
- [ ] Phương thức injection/runtime retrieval được chọn và kiểm soát permission/cache.
- [ ] Rotation có overlap, rollout, xác minh và thu hồi credential cũ.
- [ ] Incident runbook thu hồi ở cả secret manager và hệ thống đích.
- [ ] HA, degraded mode, backup/restore và recovery key đã được kiểm thử.
- [ ] Audit ghi identity/path/version/action nhưng không ghi secret value.
- [ ] Có alert cho đọc bất thường, policy drift, root token use và lease bất thường.
- [ ] CI/CD dùng identity ngắn hạn; pull request không tin cậy không đọc secret production.
- [ ] Có negative tests chứng minh workload không đọc được secret ngoài phạm vi.
- [ ] Test rotation, expiry, revoke, manager outage và log redaction.

Lưu secret trong Vault hoặc secret manager là một phần của thiết kế bảo mật API, vì credential quyết định service có thể làm gì ở hệ thống khác. Khi workload dùng identity riêng, policy giới hạn theo service/môi trường, secret được mã hóa và phân phối có kiểm soát, còn rotation/revocation/audit được vận hành đầy đủ, hệ thống sẽ giảm đáng kể phạm vi tác động khi một API hoặc credential bị xâm nhập.
