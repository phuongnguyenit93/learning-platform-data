# Secret management: Quản lý vòng đời bí mật an toàn

## 1. Secret management là gì?

**Secret management** (quản lý bí mật) là tập hợp chính sách, quy trình và biện pháp kỹ thuật để tạo, lưu trữ, cấp phát, sử dụng, giám sát, luân chuyển, thu hồi và hủy các thông tin bí mật mà con người hoặc hệ thống cần để xác thực, ký, mã hóa hoặc truy cập tài nguyên.

Một **secret** là giá trị hoặc vật liệu xác thực mà nếu bị lộ hoặc bị sử dụng trái phép có thể cho phép một chủ thể vượt qua ranh giới tin cậy. Ví dụ:

- Password và credential của tài khoản ứng dụng, database hoặc quản trị.
- API key, access token, refresh token và client secret.
- Private key dùng cho TLS, SSH, ký artifact hoặc xác thực workload.
- Certificate cùng private key tương ứng.
- Khóa mã hóa hoặc vật liệu dùng để tạo/unwrap data encryption key.
- Recovery code, webhook signing secret và shared secret giữa các dịch vụ.
- Credential dùng trong CI/CD, automation, backup và tích hợp nhà cung cấp.

Secret management không chỉ là đặt các giá trị này vào một vault. Một hệ thống quản lý bí mật phải trả lời được:

- Secret nào tồn tại, thuộc hệ thống nào và ai sở hữu?
- Ai hoặc workload nào được phép lấy secret, cho mục đích nào?
- Secret được lưu, truyền và sử dụng ở đâu?
- Có bị ghi vào source code, log, image, artifact, ticket hoặc bản sao không?
- Khi lộ hoặc hết hạn, có thể thu hồi và thay thế an toàn không?
- Bằng chứng nào cho thấy những quy tắc này đang được thực thi?

Trong module **SECURITY_SECURITY_ASSURANCE**, Secret management là một nhóm security controls cần được đánh giá từ **risk scenario → yêu cầu → thiết kế → triển khai → vận hành → bằng chứng → phát hiện → khắc phục và retest**. Một ứng dụng đọc được password từ vault chỉ chứng minh một phần luồng hoạt động; chưa chứng minh quyền truy cập tối thiểu, rotation, revoke, audit và xử lý sự cố đều hiệu quả.

> **Nguyên tắc:** bí mật chỉ được cấp cho danh tính đã xác minh, trong phạm vi và thời gian cần thiết; mọi lần sử dụng có mức truy vết phù hợp; khi bí mật bị lộ hoặc không còn cần thiết, tổ chức phải có khả năng thu hồi, thay thế và xác minh kết quả.

### 1.1. Vì sao Secret management quan trọng?

Một secret có thể là điểm vào của nhiều hệ thống. Một database password có quyền đọc toàn bộ dữ liệu khách hàng; một cloud access key có thể sửa IAM policy; một signing key bị lộ có thể làm giả artifact; một token CI/CD có thể triển khai mã độc vào production.

Rủi ro không chỉ đến từ kẻ tấn công bên ngoài:

- Developer vô tình commit file cấu hình chứa credential.
- CI job in environment variables khi build thất bại.
- Log hoặc crash report chứa Authorization header.
- Một service account dùng chung cho nhiều ứng dụng và không có owner.
- Credential dài hạn không được rotation khi nhân sự đổi vai trò.
- Backup chứa secret cũ vẫn được khôi phục và tái sử dụng.
- Nhân viên hỗ trợ hoặc automation có quyền đọc vault quá rộng.
- Một secret bị lộ nhưng không biết đang được bao nhiêu service sử dụng nên không dám thu hồi.

Secret management tốt giảm **secret sprawl**, giới hạn blast radius, cải thiện khả năng ứng cứu và tạo bằng chứng kiểm toán.

### 1.2. Secret, credential, key và certificate khác nhau thế nào?

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Secret** | Giá trị bí mật cần bảo vệ khỏi tiết lộ/sử dụng trái phép | API token, password, shared secret |
| **Credential** | Thông tin dùng để chứng minh danh tính hoặc quyền truy cập; có thể gồm secret và metadata | Username/password, certificate identity, token |
| **Cryptographic key** | Vật liệu mật mã dùng để mã hóa, giải mã, ký hoặc xác minh | AES key, private key, HMAC key |
| **Certificate** | Tài liệu số liên kết public key với danh tính/thuộc tính theo một trust model | TLS certificate |
| **Key management** | Quản lý vòng đời, chính sách sử dụng và bảo vệ khóa mật mã | Tạo, phân quyền, rotate, revoke, destroy key |
| **Secret management** | Quản lý vòng đời các bí mật/credential của người dùng và hệ thống | Vault, dynamic database credential, API token |

Các khái niệm có thể giao nhau: private key là secret cần bảo vệ và đồng thời là cryptographic key. Certificate thường chứa public key và metadata; **private key đi kèm mới là vật liệu bí mật**. Secret management và key management cần phối hợp nhưng không nên coi mọi password là một khóa mã hóa hay mọi certificate đều chứa secret.

## 2. Phân loại secret và xác định phạm vi

### 2.1. Các nhóm secret thường gặp

| Nhóm | Ví dụ | Tác động nếu lộ |
| --- | --- | --- |
| **Human account secret** | Password, recovery code, MFA seed | Chiếm tài khoản cá nhân/quản trị |
| **Application secret** | DB password, client secret, API key | Truy cập dữ liệu hoặc API của ứng dụng |
| **Machine identity material** | Workload token, service certificate, private key | Mạo danh service, truy cập liên dịch vụ |
| **Infrastructure secret** | SSH key, cloud credential, Kubernetes Secret | Chiếm hạ tầng hoặc mở rộng quyền |
| **CI/CD secret** | Deploy token, signing key, registry credential | Sửa pipeline, phát hành artifact trái phép |
| **Cryptographic material** | KEK, DEK, HMAC key, signing private key | Giải mã dữ liệu, giả mạo chữ ký hoặc xác thực |
| **Integration secret** | Webhook secret, partner API key | Giả mạo callback hoặc gọi API đối tác |
| **Recovery/emergency secret** | Break-glass credential, backup key | Vượt kiểm soát khi quy trình thường gặp sự cố |

Phân loại cần xét **mức quyền, tài nguyên, thời hạn, khả năng tái sử dụng và phạm vi phụ thuộc**, không chỉ loại dữ liệu. Một token đọc một báo cáo thử nghiệm khác rất xa token quản trị toàn bộ cloud organization.

### 2.2. Secret inventory – kiểm kê bí mật

Mỗi secret nên có hồ sơ quản lý, tối thiểu gồm:

- **Secret ID/reference:** định danh không tiết lộ giá trị secret.
- **Owner:** nhóm hoặc người chịu trách nhiệm nghiệp vụ/kỹ thuật.
- **Consumer:** ứng dụng, job, môi trường hoặc workload sử dụng.
- **Purpose:** mục đích sử dụng được phê duyệt.
- **Scope:** action, resource, tenant, environment và quyền.
- **Source/provisioning:** secret được tạo bởi ai/cơ chế nào.
- **Storage location:** vault, KMS/HSM, platform secret store hoặc cơ chế được duyệt.
- **Lifecycle:** ngày tạo, hạn, rotation policy, trạng thái và ngày review.
- **Dependencies:** service nào bị ảnh hưởng khi rotate/revoke.
- **Evidence:** approval, access logs, test run, rotation/revoke record.
- **Classification:** mức nhạy cảm và yêu cầu bảo vệ.

Không đưa **giá trị secret nguyên bản** vào inventory, spreadsheet, ticket hoặc dashboard. Dùng ID và reference để liên kết.

### 2.3. Discovery và secret sprawl

Secret có thể tồn tại trong:

- Source code, Git history, branch, pull request và issue.
- File cấu hình, build output, package, container layer.
- CI/CD variables, pipeline logs, test report và artifact.
- Cloud console, VM metadata, Kubernetes manifests và Secret objects.
- Database, cache, message queue, backup, crash dump và telemetry.
- Wiki, chat, email, ticket, clipboard và máy developer.
- Nhà cung cấp hoặc hệ thống downstream.

Một scanner tìm thấy **một giá trị trông giống API key** chưa chắc xác nhận secret thật; ngược lại, không có finding không chứng minh không có secret. Cần kết hợp discovery, xác minh theo quy trình an toàn, inventory, owner và điều tra nơi giá trị đã được sử dụng.

## 3. Threat modeling và mục tiêu kiểm soát

### 3.1. Threat scenario điển hình

| ID | Threat scenario | Hậu quả | Control cần xem |
| --- | --- | --- | --- |
| **SEC-01** | Secret bị commit vào repository public/private | Người có quyền đọc repo có thể mạo danh service | Secret scanning, revoke/rotate, history investigation |
| **SEC-02** | CI job in secret ra log | Credential bị lộ trong log/artifact | Masking, log allowlist, isolated runner |
| **SEC-03** | Workload đọc vault bằng role quá rộng | Một service bị compromise có thể lấy nhiều secret | Workload identity, scoped authorization |
| **SEC-04** | Secret dài hạn không rotation | Attacker duy trì truy cập lâu | Expiry, rotation automation, stale credential review |
| **SEC-05** | Secret đã revoke nhưng cache/session còn hiệu lực | Quyền trái phép tiếp tục hoạt động | Revoke semantics, TTL, session/token tests |
| **SEC-06** | Một secret dùng chung nhiều service | Khó xác định phạm vi, rotate gây outage | Per-workload identity, dependency inventory |
| **SEC-07** | Vault admin có thể đọc và xóa audit | Insider/attacker che dấu truy cập | Separation of duties, immutable/remote audit |
| **SEC-08** | Secret xuất hiện trong backup hoặc snapshot | Khôi phục lại bí mật cũ hoặc lộ bản sao | Backup encryption, access, retention and restore controls |
| **SEC-09** | Credential trong container image | Mọi người kéo image đều có thể lấy secret | Build-time secret exclusion, image scanning |
| **SEC-10** | Signing key bị lộ | Artifact hoặc token giả mạo | HSM/KMS, signing policy, key revocation |
| **SEC-11** | Secret bị thay thế trái phép trong vault | Service sử dụng endpoint/credential do attacker kiểm soát | Versioning, approval, integrity and change audit |
| **SEC-12** | Emergency secret dùng thường xuyên | Đường đặc quyền không được giám sát | Break-glass workflow, alert, post-use review |

Threat modeling nên làm rõ **attacker capability, trust boundary, secret scope, đường lấy secret, thời gian sử dụng và blast radius**. Không cần giả định mọi sự kiện là tấn công; lỗi quy trình và cấu hình cũng có thể tạo cùng hậu quả.

### 3.2. Security objectives có thể kiểm chứng

Ví dụ các mục tiêu:

- **SM-OBJ-01:** Mỗi workload chỉ truy cập secret được phê duyệt cho workload đó.
- **SM-OBJ-02:** Secret không xuất hiện trong source, artifact, image hoặc log ngoài các ngoại lệ được quản trị.
- **SM-OBJ-03:** Secret có owner, purpose, scope và lifecycle rõ ràng.
- **SM-OBJ-04:** Secret có thời hạn hoặc rotation/review phù hợp rủi ro.
- **SM-OBJ-05:** Khi secret bị compromise, tổ chức có thể thu hồi/thay thế và kiểm tra quyền cũ không còn hiệu lực theo thiết kế.
- **SM-OBJ-06:** Lần truy cập và thay đổi secret được audit, không ghi giá trị bí mật.
- **SM-OBJ-07:** Việc cấp phát và thay đổi secret có approval/change control phù hợp.
- **SM-OBJ-08:** Secret management service gặp lỗi không làm ứng dụng tự chuyển sang credential yếu hoặc hard-coded.
- **SM-OBJ-09:** Backup/restore và môi trường phụ không làm tái xuất hiện secret đã thu hồi.
- **SM-OBJ-10:** Có thể chứng minh bằng evidence rằng các mục tiêu trên đạt trong scope và kỳ đánh giá.

Các mục tiêu phải được chuyển thành tiêu chí chấp nhận, test và evidence cụ thể; không dùng câu “secret được bảo vệ an toàn” làm tiêu chí duy nhất.

## 4. Kiến trúc quản lý secret

### 4.1. Centralized secret store / vault

Một **secret manager/vault** tập trung cung cấp nơi lưu trữ, kiểm soát truy cập, audit và lifecycle. Tổ chức có thể dùng dịch vụ cloud, nền tảng tự quản hoặc giải pháp chuyên dụng.

Các khả năng thường cần:

- Mã hóa khi lưu và truyền.
- Authentication của người dùng/workload.
- Authorization theo secret path, namespace, project, environment và action.
- Versioning, expiry, rotation và revoke.
- Audit event cho read/write/delete/policy changes.
- Quản lý recovery/availability.
- API/SDK và cơ chế cấp secret runtime.
- Tách quyền quản trị vault, quyền đọc secret và quyền xem audit.

**Vault không tự làm secret an toàn** nếu tất cả workload dùng chung một admin token hoặc vault policy cho phép mọi ứng dụng đọc mọi secret.

### 4.2. KMS và HSM khác vault thế nào?

| Thành phần | Vai trò chính | Ví dụ |
| --- | --- | --- |
| **Secret manager/vault** | Lưu và cấp các loại secret/credential theo policy | Database password, API token, certificate reference |
| **KMS (Key Management Service)** | Quản lý cryptographic keys, policy sử dụng và thao tác mã hóa/ký tùy dịch vụ | Tạo/unwrap data key, encrypt/decrypt |
| **HSM (Hardware Security Module)** | Thiết bị/phần cứng bảo vệ vật liệu khóa và thực hiện thao tác mật mã trong boundary được kiểm soát | Bảo vệ private signing key |
| **Certificate manager/PKI** | Phát hành, gia hạn, thu hồi và kiểm tra certificate | TLS certificate cho service |
| **Identity provider** | Cấp danh tính và token cho user/workload | OIDC/OAuth identity |

Các thành phần có thể tích hợp. Vault có thể dùng KMS để mã hóa dữ liệu lưu; KMS có thể dùng HSM làm backend. Tuy nhiên, **KMS không phải kho lưu mọi password**, và HSM không thay thế quy trình cấp quyền ứng dụng.

### 4.3. Envelope encryption và secret storage

Một mô hình phổ biến là **envelope encryption**:

1. Tạo **Data Encryption Key (DEK)** để mã hóa dữ liệu.
2. Dùng **Key Encryption Key (KEK)** do KMS quản lý để bảo vệ DEK.
3. Lưu ciphertext và wrapped DEK cùng metadata cần thiết.
4. Khi đọc, workload có quyền yêu cầu KMS unwrap DEK rồi giải mã trong phạm vi cho phép.

Mô hình này giảm nhu cầu dùng trực tiếp KEK ở ứng dụng. Tuy nhiên, cần kiểm soát **ai có thể gọi decrypt/unwrap**, dữ liệu nào được giải mã, log và giới hạn sử dụng. Có mã hóa không có nghĩa người được phép giải mã là đúng.

### 4.4. Luồng cấp secret runtime

~~~mermaid
flowchart TD
    A["Workload khởi động"] --> B["Xác minh workload identity"]
    B --> C["Authorization theo service/environment"]
    C --> D{"Được phép đọc secret?"}
    D -- "Không" --> X["Từ chối + audit"]
    D -- "Có" --> E["Secret manager / vault"]
    E --> F["Cấp secret hoặc credential động"]
    F --> G["Ứng dụng sử dụng trong memory"]
    G --> H["Không log/không ghi ra artifact"]
    H --> I["Expiry / refresh / revoke"]
    I --> J["Audit và giám sát"]
~~~

Ứng dụng cần **fail safely** khi không thể lấy secret. Không tự động fallback sang password mặc định, file plaintext hoặc credential hard-coded để giữ service hoạt động.

## 5. Authentication và authorization khi truy cập vault

### 5.1. Ưu tiên workload identity

Nếu nền tảng hỗ trợ, workload nên chứng minh danh tính bằng cơ chế có thể xác minh như workload identity federation, managed identity, service certificate hoặc cơ chế tương đương. Tránh bootstrap bằng một **master secret dài hạn** được nhúng trong image.

Một workload identity cần được ràng buộc với:

- Service/application ID.
- Environment, namespace, account hoặc workload attributes.
- Trust source/issuer và audience.
- Điều kiện phát hành token.
- Quyền đọc secret cụ thể.
- Thời hạn, revoke và rotation.
- Owner chịu trách nhiệm.

Nếu một token workload có thể được dùng ở nhiều môi trường, phải chứng minh điều đó được chủ đích và có giới hạn.

### 5.2. Least privilege cho secret access

Ví dụ policy logic:

| Principal | Secret scope | Action | Kết quả mong muốn |
| --- | --- | --- | --- |
| orders-api-prod | prod/orders/db | Read current credential | Allow |
| orders-api-prod | prod/payments/signing-key | Read | Deny |
| orders-api-staging | prod/orders/db | Read | Deny |
| orders-api-prod | staging/orders/db | Read | Deny nếu không có yêu cầu riêng |
| platform-rotation-job | prod/orders/db | Rotate theo workflow | Allow có kiểm soát |
| developer-user | prod/orders/db | Read raw value | Deny theo baseline |
| vault-auditor | Audit metadata | Read logs | Allow, không mặc định đọc secret |

Không chỉ giới hạn **read**. Những action như **create, update, delete, rotate, change policy, unwrap, export, list metadata và view audit** có mức tác động khác nhau và cần tách quyền.

### 5.3. Separation of duties trong vault

Nên xem xét tách:

- Người phê duyệt nhu cầu secret.
- Người quản lý policy/role.
- Workload sử dụng secret.
- Người thực hiện rotation.
- Người review audit và incident.
- Người quản lý recovery/backup của vault.

Một admin vừa có thể đọc mọi secret, thay policy, tắt audit và xóa backup tạo ra **single point of compromise**. Với tổ chức nhỏ, có thể có kiêm nhiệm nhưng cần control bù trừ, phê duyệt và review độc lập theo mức rủi ro.

### 5.4. Authentication không thay authorization

Token vault hợp lệ chỉ chứng minh workload đã xác thực theo một cơ chế. Backend vẫn phải kiểm tra **principal được phép đọc đúng secret ID/path và thực hiện đúng action**. Không tin secret path do client tự gửi nếu path đó không được ràng buộc với identity và policy.

## 6. Vòng đời secret từ tạo đến hủy

### Bước 1. Tạo và đăng ký

- Dùng **CSPRNG** hoặc cơ chế mật mã được phê duyệt để tạo secret phù hợp.
- Không tự tạo password/token bằng timestamp, UUID không phù hợp mục tiêu hoặc dữ liệu dễ đoán.
- Gắn secret ID, owner, purpose, scope và lifecycle.
- Ghi nhận nơi sử dụng và dependency trước khi phát hành.
- Tránh in giá trị vào console, log, ticket hoặc chat.
- Chỉ cấp cho đúng người/workload qua kênh đã được phê duyệt.

Không phải secret nào cũng cần do một con người tự đặt. Credential động có thể được cấp bởi hệ thống theo policy và thời hạn.

### Bước 2. Lưu trữ và bảo vệ

- Lưu trong vault hoặc secret store được tổ chức phê duyệt.
- Mã hóa khi lưu/truyền, quản lý key và quyền truy cập.
- Hạn chế quyền export/list/read raw value.
- Không lưu secret trong source code, image, artifact hoặc file cấu hình được commit.
- Có backup/restore và recovery phù hợp cho vault, nhưng backup cũng phải được bảo vệ như dữ liệu nhạy cảm.
- Có kiểm soát truy cập, audit và retention của metadata.

### Bước 3. Cấp phát và sử dụng

- Xác thực identity của caller.
- Kiểm tra authorization theo secret, environment, purpose và action.
- Cấp secret đúng lúc, đúng scope, có hạn nếu khả thi.
- Ưu tiên dynamic credential hoặc short-lived token thay credential dài hạn.
- Hạn chế secret tồn tại trong memory/process và tránh ghi ra disk.
- Không log secret, token hoặc header nhạy cảm.
- Theo dõi việc truy cập bất thường.

### Bước 4. Luân chuyển (rotation)

**Rotation** thay secret cũ bằng giá trị mới theo lịch hoặc sự kiện. Một quy trình an toàn cần:

1. Xác định consumer và dependency.
2. Tạo credential mới hoặc phiên bản mới.
3. Cập nhật nơi cấp phát theo kế hoạch tương thích.
4. Chuyển workload sang credential mới.
5. Xác minh kết nối/hoạt động đúng.
6. Thu hồi credential cũ theo thời điểm và quy tắc đã định.
7. Kiểm tra credential cũ thực sự không còn dùng được.
8. Cập nhật inventory, version và evidence.

Với hệ thống không hỗ trợ hai credential đồng thời, có thể cần cửa sổ thay đổi hoặc cơ chế coordination để tránh outage. Không rotate một password dùng chung mà chưa biết service nào phụ thuộc.

### Bước 5. Thu hồi (revocation)

Thu hồi có thể do:

- Secret bị lộ hoặc nghi compromise.
- Workload/nhân sự không còn cần quyền.
- Hết hạn hoặc thay thế.
- Vendor/integration bị ngừng.
- Quyền truy cập bị thay đổi.
- Phát hiện secret bị dùng bất thường.

**Revoke record thành công không tự chứng minh mọi consumer đã mất quyền**. Phải kiểm tra token, session, cache, replica, credential copy và đường truy cập gián tiếp theo thiết kế.

### Bước 6. Hủy và xử lý bản sao

Khi không còn cần secret:

- Xóa/disable phiên bản theo policy và khả năng phục hồi.
- Hủy key material theo quy trình key management nếu áp dụng.
- Xử lý bản sao trong backup, snapshot và hệ thống phụ theo retention.
- Ngăn restore vô tình tái kích hoạt credential cũ.
- Giữ audit metadata cần thiết mà không giữ secret nguyên bản.
- Xác nhận dependency không còn sử dụng.

### 6.1. Rotation khác expiration và revocation

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Rotation** | Thay secret bằng giá trị mới | DB password v1 → v2 |
| **Expiration** | Secret không còn được chấp nhận sau thời điểm đã định | Token hết hạn sau 15 phút |
| **Revocation** | Chủ động làm secret/quyền không còn hiệu lực trước hoặc tại thời điểm yêu cầu | Revoke certificate hoặc API token bị lộ |
| **Deletion/destruction** | Loại bỏ secret hoặc vật liệu khóa khỏi nơi quản lý theo quy trình | Hủy private key cũ khi không còn cần |
| **Renewal** | Gia hạn hoặc phát hành lại vật liệu theo quy trình | Cấp certificate mới trước ngày hết hạn |

Rotation không nhất thiết đồng nghĩa secret cũ bị revoke ngay; một số hệ thống có giai đoạn overlap. **Overlap phải có thời hạn, scope và điều kiện rõ**, nếu không secret cũ có thể tiếp tục được dùng vô thời hạn.

## 7. Dynamic secrets và short-lived credentials

### 7.1. Dynamic secret là gì?

**Dynamic secret** được tạo hoặc cấp theo yêu cầu, thường có thời hạn và quyền cụ thể, thay vì dùng một password tĩnh chung cho nhiều ứng dụng.

Ví dụ: khi orders-api cần truy cập database, secret manager cấp một credential có:

- Database role chỉ cho phép đọc/ghi những schema cần thiết.
- TTL 20 phút hoặc thời hạn theo policy.
- Lease/reference để gia hạn hoặc thu hồi.
- Audit event gắn với workload identity.
- Quy trình xử lý khi credential hết hạn.

Ưu điểm là giảm thời gian phơi nhiễm và secret reuse. Tuy nhiên, dynamic secrets đòi hỏi quản lý **lease, renewal, revoke, connection pool, outage và dependency** tốt.

### 7.2. Lease lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> ISSUED: Identity + policy hợp lệ
    REQUESTED --> DENIED: Không đủ quyền
    ISSUED --> ACTIVE: Consumer sử dụng
    ACTIVE --> RENEWED: Renew được phép
    ACTIVE --> EXPIRED: Hết TTL
    ACTIVE --> REVOKED: Thu hồi chủ động
    RENEWED --> ACTIVE
    EXPIRED --> [*]
    REVOKED --> [*]
    DENIED --> [*]
~~~

Cần kiểm chứng:

- Lease có ràng buộc đúng principal và resource?
- TTL được thực thi ở dịch vụ đích hay chỉ ở vault?
- Khi revoke, database/token service có thực sự vô hiệu credential?
- Connection pool còn giữ session đã xác thực không?
- Renewal có thể kéo dài quyền vô hạn không?
- Nếu vault mất kết nối, consumer xử lý thế nào?
- Audit có ghi cấp, renew, expire và revoke mà không ghi secret?

### 7.3. Short-lived không tự động là least privilege

Token sống 5 phút nhưng có quyền quản trị toàn bộ tổ chức vẫn có blast radius lớn trong 5 phút đó. Cần kết hợp **scope hẹp, audience, issuer, subject, action, resource, conditions và TTL**.

## 8. Secrets trong CI/CD và software supply chain

### 8.1. Những vị trí dễ rò rỉ

- Repository, Git history, fork và pull request.
- CI variables, runner environment và debug output.
- Build logs, test reports, artifacts, package registry.
- Dockerfile ARG/ENV, image layer và build cache.
- Deployment manifests, Helm values và generated config.
- Release signing, registry push và deployment token.
- Chat/issue được bot tự động đính kèm output.

### 8.2. Control cần thiết

- **Secret scanning** ở commit, repository và CI; có quy trình xử lý finding.
- **OIDC/workload federation** hoặc cơ chế identity tương đương để tránh static cloud keys khi có thể.
- Credential tách theo **repo, workflow, branch, environment và job**.
- Approval cho production deploy và signing action.
- Không echo environment hoặc in exception có secret.
- BuildKit/secret mount hoặc cơ chế build secret an toàn; không đưa secret vào image layer.
- Artifact signing key được bảo vệ, có quyền và audit riêng.
- Runner isolation, hạn chế người có quyền đọc log và artifact.
- Khi lộ, **revoke/rotate trước**, rồi mới dọn history và bản sao theo kế hoạch.

**Xóa secret khỏi commit mới không xóa nó khỏi Git history hoặc fork.** Cần giả định credential đã lộ, xử lý vòng đời secret và xác minh nơi có thể còn bản sao.

### 8.3. Secret scanning và xử lý finding

Một finding cần ghi:

- Repository/path/commit/reference, không copy secret vào ticket.
- Loại secret và confidence của detector.
- Owner/consumer và quyền mà secret có.
- Trạng thái đã xác minh hay false positive.
- Mốc phát hiện, revoke/rotate và retest.
- Các bản sao/log/artifact cần xử lý.
- Phạm vi truy cập có thể đã xảy ra.
- Reviewer và quyết định risk.

Không để một bot gửi **giá trị secret nguyên văn** vào chat hoặc issue công khai khi báo lỗi.

## 9. Secrets trong cloud, containers và Kubernetes

### 9.1. Cloud workload

Ưu tiên identity do nền tảng cấp và token ngắn hạn nếu phù hợp. Hạn chế access key dài hạn trong user data, startup script, image hoặc file config.

Kiểm tra:

- Role trust policy và condition.
- Scope tài nguyên và quyền decrypt/read.
- Metadata service và khả năng SSRF lấy credential.
- Credential trong snapshot, disk, backup và support bundle.
- Audit các lần assume role, read secret và policy change.
- Rotation và revoke khi account/workload bị compromise.

### 9.2. Kubernetes

Kubernetes Secret object **không tự đảm bảo secret được mã hóa mạnh tại rest** trong mọi cấu hình. Cần kiểm tra:

- Encryption at rest cho dữ liệu lưu trong etcd theo cấu hình nền tảng.
- RBAC giới hạn get/list/watch Secret.
- Service account và workload identity riêng theo namespace/service.
- Không đưa secret vào manifest được commit hoặc image.
- Hạn chế mount secret vào container không cần.
- Kiểm soát node, debug/exec, privileged pod và quyền đọc filesystem.
- Audit API access và thay đổi Secret/RoleBinding.
- Rotation, rollout và xử lý pod/connection còn dùng giá trị cũ.

Không coi base64 encoding là encryption. Base64 chỉ là biểu diễn dữ liệu.

### 9.3. Container image và runtime

- Không bake secret vào image.
- Kiểm tra image layer/history và build cache.
- Cấp secret lúc runtime qua cơ chế được phê duyệt.
- Chỉ mount vào container cần dùng.
- Hạn chế đọc file/metadata qua process khác.
- Không in environment variables khi debug.
- Xử lý crash dump/core dump theo policy.
- Rebuild/redeploy khi secret bị lộ và kiểm tra image cũ.

## 10. Java/Spring Boot: tích hợp Secret Manager an toàn

### 10.1. Cấu hình không chứa giá trị bí mật

Một ứng dụng Spring Boot có thể nhận **reference** tới secret thay vì hard-code giá trị:

~~~yaml
spring:
  application:
    name: orders-api
app:
  secrets:
    provider: approved-secret-manager
    database:
      secret-id: "prod/orders/database"
      refresh-before-expiry: "PT2M"
~~~

File cấu hình trên chỉ chứa **secret ID/reference**, không chứa password. approved-secret-manager là tên provider minh họa, không phải tên sản phẩm cụ thể. Authentication để đọc secret phải dựa trên workload identity hoặc cơ chế đã được phê duyệt.

### 10.2. Abstraction cho Secret Provider

~~~java
public interface SecretProvider {
    SecretValue get(String secretId);
}

public record SecretValue(
        String value,
        String version,
        Instant expiresAt) {
}
~~~

Không nên để mọi business service tự gọi API vault với policy khác nhau. Một abstraction giúp thống nhất xử lý lỗi, metadata, version và audit, nhưng bản thân interface không tạo security control nếu implementation và authorization không được kiểm tra.

### 10.3. Service lấy secret theo identity runtime

~~~java
@Service
public class DatabaseCredentialService {
    private final SecretProvider secretProvider;

    public DatabaseCredentialService(SecretProvider secretProvider) {
        this.secretProvider = secretProvider;
    }

    public SecretValue currentCredential() {
        // Workload identity duoc nen tang xac minh.
        // Provider chi cho phep doc secret cua orders-api trong env nay.
        return secretProvider.get("prod/orders/database");
    }
}
~~~

Ví dụ minh họa. Trong hệ thống thực, secret ID nên đến từ cấu hình đã được kiểm soát, nhưng **authorization phải được vault xác minh ở server-side**. Không tin một caller chỉ vì họ tự gửi secret path.

### 10.4. Không log secret

~~~java
try {
    SecretValue credential = databaseCredentialService.currentCredential();
    connectUsing(credential.value());
    log.info("Database credential loaded; version={}", credential.version());
} catch (SecretAccessDeniedException ex) {
    log.error("Database credential access denied; correlationId={}",
            correlationId);
    throw ex;
}
~~~

Không log credential.value(), exception chứa raw response, connection URL có password hoặc toàn bộ object. Metadata như **secret version, correlation ID và kết quả** có thể đủ cho điều tra.

### 10.5. Dynamic credential và connection pool

Nếu secret được rotate, connection pool có thể tiếp tục giữ kết nối đã xác thực bằng credential cũ. Cần thiết kế:

- Credential provider quản lý version và expiry.
- Pool tạo connection mới bằng credential mới.
- Connection cũ được drain/recycle có kiểm soát.
- Không đóng đồng loạt mọi connection gây outage.
- Sau revoke, xác minh session cũ bị ảnh hưởng như thế nào.
- Có retry/backoff và alert khi secret manager không sẵn sàng.
- Không fallback sang password cũ hoặc hard-coded.

Rotation database credential cần phối hợp **vault, database account, application pool và deployment**. Một cron job thay giá trị trong vault nhưng không cập nhật database hoặc connection pool chưa phải rotation thành công.

## 11. Secret rotation không gián đoạn

### 11.1. Rotation có overlap

Với dịch vụ hỗ trợ hai credential đồng thời, một chiến lược có thể là:

1. Tạo credential mới với quyền tương đương hoặc hẹp hơn.
2. Cấp version mới trong vault.
3. Cho workload chuyển sang version mới.
4. Xác minh các consumer đã dùng version mới.
5. Thu hồi credential cũ.
6. Kiểm tra credential cũ không còn được chấp nhận.
7. Đóng rotation event và lưu evidence.

~~~mermaid
sequenceDiagram
    participant O as Rotation Orchestrator
    participant V as Vault
    participant DB as Database
    participant A as Orders API
    O->>DB: Tạo credential version mới
    DB-->>O: Credential mới sẵn sàng
    O->>V: Lưu version mới
    V-->>A: Cấp version mới theo policy
    A->>DB: Kết nối bằng credential mới
    DB-->>A: Kết nối thành công
    A-->>O: Consumer xác nhận version mới
    O->>DB: Thu hồi credential cũ
    O->>V: Đánh dấu version cũ revoked
    O->>DB: Kiểm tra credential cũ bị từ chối
    O->>V: Ghi kết quả và đóng rotation
~~~

Sơ đồ là luồng minh họa; không phải database nào cũng hỗ trợ hai credential hoặc kiểm tra consumer tự động. Với hệ thống không hỗ trợ overlap, cần kế hoạch downtime/change window hoặc cơ chế chuyển đổi khác có kiểm soát.

### 11.2. Rotation và rollback

Rollback không nên có nghĩa **mở lại secret đã bị compromise**. Nếu version mới gây lỗi:

- Chẩn đoán nguyên nhân và giữ secret cũ chỉ khi chưa bị thu hồi và chưa có dấu hiệu compromise.
- Nếu secret cũ bị lộ, tạo version mới khác và sửa consumer.
- Có thể tạm dừng chức năng phụ thuộc thay vì phục hồi credential nguy hiểm.
- Ghi quyết định và người phê duyệt.
- Retest cả hoạt động bình thường và trạng thái revoke.

## 12. Xử lý secret bị lộ (secret compromise)

Khi secret bị lộ hoặc có dấu hiệu sử dụng trái phép, cần coi đó là **sự kiện bảo mật cần đánh giá và ứng cứu**, không chỉ là công việc xóa một dòng code.

### 12.1. Quy trình ứng phó

1. **Triage:** xác định loại secret, quyền, owner, nơi phát hiện và confidence.
2. **Containment:** revoke/disable hoặc giảm quyền ngay theo thẩm quyền và mức rủi ro.
3. **Rotate:** cấp secret mới, cập nhật consumer và dependency.
4. **Scope investigation:** repository, history, logs, artifacts, image, backup, CI runner, chat, endpoint và vendor.
5. **Usage review:** xem audit/API access, thời điểm và tài nguyên có thể bị truy cập.
6. **Credential cleanup:** loại bỏ bản sao và cấu hình cũ theo quy trình.
7. **Recovery:** xác minh dịch vụ dùng secret mới, session/token cũ không còn quyền trái phép.
8. **Root cause:** vì sao secret bị lộ và control nào không ngăn/phát hiện.
9. **Retest:** thử lại đường lộ, kiểm tra secret cũ bị từ chối và các đường tương tự.
10. **Lessons learned:** cập nhật inventory, policy, scanner, training và monitoring.

### 12.2. Không xóa evidence trong lúc ứng cứu

Cần bảo toàn **metadata và audit trail** phù hợp để điều tra: secret ID, version, timestamps, actor, source, destination và hành động. Tránh sao chép secret nguyên bản vào ticket hoặc chat. Nếu cần lưu vật chứng, dùng kho evidence được bảo vệ và giới hạn quyền.

### 12.3. Phân loại finding

| Loại gap | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Discovery gap** | Không phát hiện secret trong image | Mở rộng scanner/inventory |
| **Storage gap** | Secret lưu plaintext trong config | Di chuyển sang approved store và revoke bản cũ |
| **Identity gap** | Workload dùng token dùng chung | Cấp identity riêng, scoped authorization |
| **Scope gap** | Service đọc được secret của môi trường khác | Sửa policy và negative tests |
| **Lifecycle gap** | Secret quá hạn nhưng vẫn active | Expiry/rotation/revoke automation |
| **Logging gap** | Authorization header xuất hiện trong trace | Redaction, log schema, incident review |
| **Rotation gap** | Vault version đổi nhưng consumer dùng giá trị cũ | Rotation orchestration và connection verification |
| **Revocation gap** | Credential bị revoke nhưng session vẫn hoạt động | Token/session/database revoke design |
| **Audit gap** | Admin có thể xóa dấu vết đọc secret | Tách quyền, remote/immutable logging |
| **Evidence gap** | Không chứng minh được secret cũ bị vô hiệu | Test trực tiếp và lưu kết quả |

## 13. Đánh giá hiệu quả Secret management

### 13.1. Design, implementation và operating effectiveness

| Lớp đánh giá | Câu hỏi | Evidence |
| --- | --- | --- |
| **Design effectiveness** | Kiến trúc có giảm rủi ro secret sprawl, misuse, long-lived access và blast radius? | Threat model, data/secret flow, policy, identity design, rotation/revoke plan |
| **Implementation effectiveness** | Vault, workload identity, IAM, injection, logging và automation có được cấu hình đúng? | Config snapshot, code review, IaC, deployment records, integration tests |
| **Operating effectiveness** | Secret được cấp, dùng, rotate, revoke, review và xử lý sự cố đúng qua kỳ? | Vault audit, rotation runs, revoke tests, access reviews, incident records |

Một secret manager đã được triển khai **không chứng minh** mọi ứng dụng đều dùng nó. Một rotation job chạy thành công **không chứng minh** credential cũ không còn hiệu lực. Cần kiểm tra **consumer thực tế, quyền đích và hành vi sau thay đổi**.

### 13.2. Security claims và test

| Security claim | Kiểm thử/kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| Chỉ workload đúng được đọc secret | Identity A đọc secret A/B; identity B thử đọc A | Allow đúng phạm vi, deny ngoài scope |
| Secret không nằm trong source/artifact | Repo/history/image/artifact scan | Không có secret thật chưa xử lý |
| Secret không xuất hiện trong log | Canary secret và kiểm tra log/trace/crash output | Không lưu raw value |
| Secret có lifecycle/owner | Inventory sample và owner review | Có owner, purpose, expiry/rotation |
| Rotation thay thế được credential | Thực hiện rotation trong test environment | Consumer chuyển sang version mới |
| Credential cũ bị vô hiệu | Thử truy cập bằng credential cũ | Bị từ chối theo policy |
| Revoke có hiệu lực | Revoke token/credential, thử lại qua session/API | Không tiếp tục sử dụng trái phép |
| Vault failure không tạo fallback yếu | Mô phỏng timeout/unavailable | Không dùng hard-coded/default secret |
| Audit truy vết được | Read/write/policy-change test | Actor, secret ID, action, time, result |
| Backup không tái kích hoạt secret cũ | Restore test và kiểm tra trạng thái revoke | Secret cũ không được sử dụng trái policy |

### 13.3. Chất lượng evidence

Evidence nên có:

- Secret ID/reference, loại, owner, consumer và purpose.
- Policy/role version, environment, service/build.
- Test scenario, expected/actual result, thời điểm và reviewer.
- Rotation/revoke event ID và version cũ/mới (không phải giá trị).
- Audit metadata và trạng thái integrity.
- Population/scope, sampling method và giới hạn.
- Finding, action owner, deadline, retest và residual risk decision.

**Không lưu giá trị secret vào evidence** chỉ để chứng minh một lần đọc hoặc rotation. Một record secret_rotated=true không đủ nếu thiếu xác minh consumer và credential cũ.

### 13.4. Trạng thái kết luận

- **Effective in assessed scope:** có bằng chứng phù hợp cho các tiêu chí trong scope/kỳ.
- **Partially effective:** một phần đạt, còn consumer, môi trường hoặc lifecycle chưa bao phủ.
- **Ineffective:** có bằng chứng control thất bại, như secret cũ vẫn truy cập được sau revoke.
- **Insufficient evidence:** chưa đủ căn cứ kết luận.
- **Exception approved:** có ngoại lệ và residual risk được phê duyệt đúng thẩm quyền; không đồng nghĩa control đạt.
- **Not applicable:** có lý do và cấp xác nhận phù hợp rằng control không áp dụng.

Không suy “không có secret leak trong incident log” thành “không có secret bị lộ”; detection coverage cũng phải được đánh giá.

## 14. KPI/KRI cho chương trình Secret management

| Chỉ số | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| **Secret inventory coverage** | Tỷ lệ secret/workload đã có owner, purpose, scope | Tổng thể có thể chưa đầy đủ |
| **Vault adoption coverage** | Tỷ lệ ứng dụng trong scope dùng approved secret store/identity | Không chứng minh quyền đã hẹp |
| **Long-lived credential exposure** | Số lượng/phạm vi credential dài hạn còn active | Một credential có quyền rất lớn có thể quan trọng hơn nhiều credential nhỏ |
| **Rotation compliance** | Credential được rotate theo policy | Không chứng minh consumer đã chuyển và secret cũ bị revoke |
| **Revocation verification rate** | Số revoke được xác minh bằng test / số revoke thuộc mẫu | Phải test session/cache/consumer |
| **Overprivileged access findings** | Principal đọc được secret ngoài scope | Severity theo quyền và blast radius |
| **Secret scanning findings** | Finding theo repo/image/log và trạng thái xử lý | Có false positive/false negative |
| **Time to revoke after compromise** | Thời gian từ xác nhận tới revoke | Cần định nghĩa mốc phát hiện/xác nhận |
| **Rotation failure rate** | Rotation thất bại hoặc consumer chưa cập nhật | Cần xem ảnh hưởng dịch vụ và cách retry |
| **Secrets in logs/artifacts** | Kết quả kiểm tra secret exposure | Không có finding không chứng minh tuyệt đối |
| **Orphaned secret count** | Secret không owner/consumer rõ | Cần xác minh dependency trước khi xóa |
| **Audit coverage** | Access/change events có đủ metadata | Log có thể bị thiếu hoặc bị sửa |
| **Exception age** | Ngoại lệ quá hạn và rủi ro còn lại | Ngoại lệ không phải trạng thái đạt |
| **Verified remediation time** | Thời gian đến khi retest đạt | Không dừng tại lúc merge PR |

Ví dụ: tổ chức có 120 secret trong inventory, 96 secret có owner và consumer đã được xác minh. **Inventory ownership coverage = 96/120 = 80%**. Con số này không nói 80% secret an toàn; 24 secret chưa rõ owner có thể bao gồm credential quản trị quan trọng nhất.

### 14.1. Không tối ưu KPI bằng cách che giấu secret

Nếu mục tiêu chỉ là giảm số secret scanner finding, đội có thể tắt rule hoặc gắn nhãn false positive mà không điều tra. Cần đo thêm **coverage, confirmed exposure, revoke time, retest và recurrence**, đồng thời review các thay đổi rule.

## 15. Governance, exception và trách nhiệm

### 15.1. Quản lý ngoại lệ

Một ngoại lệ có thể cần khi hệ thống cũ chưa hỗ trợ vault hoặc đối tác chỉ hỗ trợ credential tĩnh. Ngoại lệ cần:

- Secret ID/nhóm secret, consumer và môi trường.
- Lý do kỹ thuật/nghiệp vụ.
- Quyền, scope và thời hạn tồn tại.
- Risk assessment và control bù trừ.
- Owner, người phê duyệt và ngày hết hạn.
- Kế hoạch chuyển đổi/rotation.
- Evidence giám sát và điều kiện thu hồi.

Không cấp ngoại lệ vô thời hạn chỉ vì “ứng dụng legacy”. Ngoại lệ không miễn trừ nghĩa vụ bắt buộc và không biến control không đạt thành effective.

### 15.2. RACI minh họa

*R = thực hiện; A = chịu trách nhiệm cuối cùng; C = tham vấn; I = thông báo.*

| Hoạt động | Secret/Vault owner | Application owner | Platform/SRE | Risk owner | Assurance/Audit |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa secret policy và baseline | **A/R** | C | C | C | C |
| Đăng ký owner, consumer và purpose | C | **A/R** | R | I | C |
| Cấu hình workload identity và vault policy | **A** | C | R | I | C |
| Tích hợp secret runtime vào ứng dụng | C | **A** | R | I | C |
| Rotation và revoke | **A** | R | R | I | C |
| Ứng phó secret compromise | C | R | R | **A** | I |
| Đánh giá độc lập bằng chứng | C | C | C | I | **A/R** |
| Chấp nhận residual risk theo quyền | C | C | C | **A/R** | I |
| Retest và đóng finding | C | **A** | R | C | C |

Ma trận cần được điều chỉnh theo cơ cấu thật. Tách quyền **đọc secret**, **sửa policy**, **thực hiện rotation** và **xem audit** khi mức rủi ro yêu cầu.

## 16. Mẫu hồ sơ Secret management assurance

YAML dưới đây là **mẫu giả định**, chưa chứa kết quả kiểm tra thực tế:

~~~yaml
assessment_id: "SECRET-MGMT-DEMO-007"
control_id: "CTRL-SECRET-LIFECYCLE-01"
title: "Workload secret lifecycle assurance"
control_owner: "Platform Security Owner"
application_owner: "Orders API Owner"
risk_owner: "Orders Product Owner"
policy_ref: "POL-SECRET-MANAGEMENT"
standard_ref:
  id: "STD-WORKLOAD-CREDENTIALS"
  version: "demo-1.0"
scope:
  service: "orders-api"
  environment: "integration"
  build: "demo-build-not-verified"
  secret_refs:
    - "prod/orders/database"
    - "integration/orders/database"
security_claims:
  - "Only the intended workload can read its secret"
  - "Secret values do not appear in source, artifacts or logs"
  - "Rotation updates consumers and revokes old credentials"
  - "Compromised credentials can be revoked and verified"
evidence_plan:
  - "Workload identity and vault policy review"
  - "Cross-service negative access tests"
  - "Repository/image/log secret scan"
  - "Rotation and old-credential rejection test"
  - "Vault audit and backup restore review"
design_review: "PENDING"
implementation_review: "NOT_VERIFIED"
operating_review: "NOT_VERIFIED"
evidence_refs: []
assessment_conclusion: "INSUFFICIENT_EVIDENCE"
confidence: "LOW"
findings: []
next_action: "Execute scoped access and lifecycle tests"
exception:
  approved: false
  approver: null
~~~

Hồ sơ thực cần thêm thời gian, reviewer, test run ID, policy version, population, phạm vi production nếu có, kết quả cụ thể, finding và quyết định rủi ro. **Không điền secret value vào YAML hoặc ticket.**

## 17. Các sai lầm phổ biến

### 17.1. Nghĩ rằng có vault là đã an toàn

Vault có thể có policy quá rộng, token bootstrap dùng chung hoặc admin có thể đọc mọi secret.

**Cách xử lý:** kiểm tra identity, authorization, separation of duties, audit và từng consumer.

### 17.2. Hard-code secret trong cấu hình rồi chỉ mã hóa repository

Mã hóa file không giải quyết việc key giải mã nằm cùng repo hoặc developer có thể lấy plaintext.

**Cách xử lý:** dùng secret store/identity runtime, giới hạn người đọc và kiểm tra artifact/log.

### 17.3. Chỉ rotation mà không revoke

Credential cũ vẫn hoạt động trong giai đoạn overlap kéo dài hoặc bị quên.

**Cách xử lý:** có expiry, deadline revoke và test credential cũ bị từ chối.

### 17.4. Dùng một secret cho nhiều service

Khi lộ, không biết blast radius; khi rotate, có thể làm nhiều service gián đoạn.

**Cách xử lý:** identity/credential riêng theo workload, purpose và environment.

### 17.5. Đưa secret vào container image

Secret có thể nằm trong layer/history dù đã xóa file ở layer sau.

**Cách xử lý:** inject lúc runtime, kiểm tra image/layer và rotate secret đã lộ.

### 17.6. Cho developer đọc production secret mặc định

Tạo rủi ro insider, laptop compromise và bản sao khó kiểm soát.

**Cách xử lý:** phân tách dev/prod, break-glass có phê duyệt, debug qua dữ liệu giả lập hoặc quyền tạm thời.

### 17.7. Log response từ vault để debug

Response có thể chứa token hoặc secret nguyên bản.

**Cách xử lý:** log error code, secret reference, correlation ID và version; redact response.

### 17.8. Xem secret path là quyền

Tên path khó đoán không phải authorization.

**Cách xử lý:** server-side policy kiểm tra principal, action, resource và environment.

### 17.9. Rotate DB password nhưng không kiểm tra connection pool

Pool vẫn có thể dùng connection cũ, hoặc app không kết nối được sau khi revoke.

**Cách xử lý:** kiểm thử pool drain, credential switch, revoke và availability.

### 17.10. Coi secret scan không có finding là bằng chứng không rò rỉ

Scanner có thể không nhận diện format hoặc kênh mới.

**Cách xử lý:** kiểm tra coverage, false negative, history, image, log và hệ thống phụ.

### 17.11. Revoke token nhưng bỏ qua session và cache

Quyền cũ có thể còn tồn tại ở consumer.

**Cách xử lý:** test từ góc nhìn resource đích, token/session TTL và cache invalidation.

### 17.12. Đưa secret vào ticket để dễ bàn giao

Ticket có nhiều người xem và retention dài.

**Cách xử lý:** dùng secret reference, không gửi giá trị; nếu đã lộ, xử lý như compromise.

### 17.13. Dùng credential khẩn cấp thường ngày

Break-glass trở thành đường quản trị không được kiểm soát.

**Cách xử lý:** giới hạn tình huống, alert, review và rotate sau sử dụng.

### 17.14. Đóng finding sau khi xóa file khỏi Git

Git history, fork, runner cache, artifact và log có thể còn secret.

**Cách xử lý:** revoke/rotate, điều tra bản sao và retest toàn bộ đường liên quan.

## 18. Checklist thiết kế và đánh giá Secret management

- [ ] Có inventory secret với ID, owner, consumer, purpose, scope và lifecycle.
- [ ] Đã xác định human, workload, CI/CD, cloud, DB, signing và emergency secrets.
- [ ] Không ghi secret nguyên bản vào inventory, ticket, chat hoặc audit evidence.
- [ ] Secret được tạo bằng cơ chế ngẫu nhiên/mật mã phù hợp.
- [ ] Secret được lưu trong approved vault/store hoặc có ngoại lệ được quản trị.
- [ ] Workload identity được xác thực; tránh bootstrap bằng master secret dài hạn.
- [ ] Vault authorization giới hạn theo secret, action, environment và workload.
- [ ] Có tách quyền đọc, thay policy, rotate, revoke và audit theo rủi ro.
- [ ] Secret không xuất hiện trong source, Git history, artifact, image, build log và telemetry ngoài kiểm soát.
- [ ] Runtime injection có scope; không fallback sang hard-coded/default credential.
- [ ] Có rotation/expiry/revoke policy và dependency inventory.
- [ ] Rotation xác minh consumer dùng version mới và credential cũ bị từ chối.
- [ ] Đã test token/session/cache/connection pool sau revoke.
- [ ] Dynamic credentials có lease, renewal, expiry và revoke rõ.
- [ ] Backup/restore không làm tái xuất hiện secret đã thu hồi trái policy.
- [ ] Audit có actor, secret reference, action, time, result; không chứa secret value.
- [ ] Có cảnh báo truy cập bất thường, policy change và break-glass use.
- [ ] Có quy trình compromise response: contain, revoke, rotate, investigate, retest.
- [ ] Có kiểm tra secret scanning coverage và xử lý finding.
- [ ] Ngoại lệ có owner, approver, risk, hạn và control bù trừ.
- [ ] Bằng chứng gắn policy version, build, environment, thời gian và reviewer.
- [ ] Findings có action owner, due date, closure criteria và retest.
- [ ] Có trigger đánh giá lại khi đổi workload, vault, pipeline, vendor hoặc quyền.
- [ ] Kết luận ghi rõ scope, confidence, phần chưa xác minh và residual risk.

Checklist hỗ trợ thực hiện; đánh dấu đủ ô không thay thế kiểm tra quyền truy cập, rotation, revoke và vận hành trên hệ thống thật.

## 19. Câu hỏi tự kiểm tra

1. Secret khác credential, cryptographic key và certificate thế nào?
2. Vì sao một secret trong Git history vẫn cần được xem là đã lộ dù commit mới đã xóa file?
3. Secret inventory nên có những metadata nào và vì sao không nên chứa secret value?
4. Vault khác KMS và HSM ở chức năng nào?
5. Workload identity giảm nhu cầu lưu credential bootstrap dài hạn ra sao?
6. Vì sao một token ngắn hạn vẫn nguy hiểm nếu có quyền quá rộng?
7. Rotation khác expiration và revocation thế nào?
8. Làm sao chứng minh credential cũ thật sự không còn được chấp nhận sau rotation?
9. Dynamic secret cần quản lý lease và connection pool ra sao?
10. Vì sao base64 trong Kubernetes Secret không phải encryption?
11. Những đường nào có thể làm secret rò ngoài source code?
12. Secret scanner có thể có false positive và false negative thế nào?
13. Khi secret bị lộ, tại sao revoke/rotate phải đi cùng investigation và kiểm tra bản sao?
14. Vì sao log vault cần metadata nhưng không nên ghi secret value?
15. Làm sao tách quyền vault administrator, secret consumer và auditor?
16. Nếu vault unavailable, ứng dụng nên xử lý thế nào để không fallback sang credential yếu?
17. Backup restore có thể làm credential cũ quay lại bằng cách nào?
18. Trong Spring Boot, vì sao đọc secret thành công không chứng minh secret access được giới hạn đúng?
19. Test nào chứng minh một workload không đọc được secret của service khác?
20. Bằng chứng nào cần có trước khi đóng finding về secret bị lộ trong CI log?

## 20. Tổng kết

**Secret management** là quản lý **toàn bộ vòng đời bí mật** từ tạo, kiểm kê, lưu trữ, cấp quyền, sử dụng, rotation, revoke đến hủy và xử lý sự cố. Một chương trình tốt cần **inventory đầy đủ, owner và purpose rõ, workload identity, least privilege, vault/KMS/HSM đúng vai trò, runtime injection an toàn, short-lived/dynamic credentials, audit bảo vệ và quy trình compromise response**. Có vault, bật mã hóa hoặc chạy secret scanner không tự chứng minh secret được kiểm soát. Trong **SECURITY_SECURITY_ASSURANCE**, mỗi kết luận phải liên kết **risk → requirement → control → test/audit/evidence → finding → remediation → retest**, xác minh cả consumer và hành vi credential cũ sau rotation/revoke, đồng thời ghi đúng phạm vi và residual risk. Khi ứng dụng, pipeline, workload và nhà cung cấp thay đổi, inventory và assurance của secret cũng phải được cập nhật liên tục.
