# Secret manager — Quản lý vòng đời và cấp phát bí mật an toàn

Một backend cần mật khẩu database, khóa ký webhook và credential để gọi dịch vụ thanh toán. Nhóm phát triển ban đầu đặt các giá trị này trong file cấu hình, sau đó chuyển sang biến môi trường. Khi một log debug vô tình in toàn bộ cấu hình lúc khởi động, credential bị lộ. Nhóm đổi mật khẩu database nhưng quên cập nhật một worker batch đang chạy; một số request bắt đầu lỗi. Họ lại tạo một credential mới dùng chung cho nhiều service để khắc phục nhanh, khiến phạm vi ảnh hưởng lớn hơn.

**Secret manager** là hệ thống tập trung để lưu trữ, kiểm soát truy cập, cấp phát, xoay vòng, thu hồi và kiểm toán các bí mật mà ứng dụng hoặc workload cần dùng. Bí mật có thể là password, API key, access token, private key, signing key, database credential hoặc certificate material. Secret manager giúp quản lý vòng đời và phân phối có kiểm soát; nó không tự xác minh người gọi, không tự làm cho ứng dụng an toàn và không loại bỏ nhu cầu bảo vệ bí mật trong lúc sử dụng.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, bài học này kết nối credential storage với workload identity, authentication, key management và trust boundary. Người học sẽ biết cách phân loại bí mật, thiết kế quyền truy cập tối thiểu, dùng KMS/HSM và envelope encryption, cấp secret động có lease, triển khai rotation/revocation, chọn cách đưa secret vào workload, và ứng phó khi bí mật bị lộ. Mục tiêu là để đúng workload nhận đúng secret cho đúng mục đích trong thời gian cần thiết, với khả năng audit và thu hồi rõ ràng.

## 1. Secret manager giải quyết vấn đề gì?

Secret manager cung cấp một nơi có kiểm soát để lưu và cấp phát bí mật. Thay vì nhúng credential trong source code hoặc image, workload xác thực bằng danh tính của nó rồi yêu cầu secret được phép truy cập.

Các chức năng thường gặp:

- Lưu trữ bí mật đã mã hóa và quản lý phiên bản.
- Xác thực caller bằng workload identity, client certificate hoặc cơ chế bootstrap được kiểm soát.
- Authorization theo principal, secret path, namespace, environment và operation.
- Cấp secret tĩnh hoặc tạo credential động theo yêu cầu.
- Lease, TTL, renewal và revocation.
- Rotation có phối hợp với consumer.
- Audit ai đã đọc, tạo, cập nhật, rotate hoặc revoke secret.
- Replication, backup, recovery và high availability.
- Tích hợp KMS/HSM để bảo vệ encryption key hoặc signing key.

Secret manager không thay thế:

- **Identity provider:** xác minh danh tính người dùng hoặc workload.
- **Authorization policy:** quyết định principal được làm gì với secret nào.
- **KMS/HSM:** quản lý và bảo vệ key mã hóa/ký ở cấp cryptographic.
- **Application security:** ngăn log secret, kiểm soát memory, dependency và access tới dữ liệu.
- **Incident response:** phát hiện và xử lý credential compromise.

Một secret manager cấu hình sai có thể trở thành kho tập trung chứa mọi bí mật với quyền truy cập quá rộng. Vì vậy, thiết kế trust boundary và policy quan trọng ngang với lựa chọn sản phẩm.

## 2. Phân biệt secret, key, certificate và configuration

Không phải mọi giá trị cấu hình đều là secret. Phân loại đúng giúp chọn cơ chế bảo vệ và rotation phù hợp.

| Loại dữ liệu | Ví dụ | Có cần giữ bí mật? | Cách quản lý |
| --- | --- | --- | --- |
| Configuration | Hostname, feature flag không nhạy cảm, timeout | Thường không | Config service hoặc version control |
| Password/credential | Database password, API key, client secret | Có | Secret manager, hash nếu dùng để xác minh password |
| Access token | Bearer token, refresh token | Có | Token service/secret manager tùy vòng đời và workload |
| Cryptographic key | AES key, HMAC key, private signing key | Có, mức bảo vệ cao | KMS/HSM hoặc key vault |
| Certificate | X.509 certificate public | Thường không; private key đi kèm là bí mật | PKI/certificate manager |
| Recovery material | Recovery code, reset token | Có, thường one-time | Lưu hash hoặc secret store với TTL |
| Identity metadata | Workload ID, issuer, audience | Không nhất thiết bí mật | Identity system/configuration; vẫn cần integrity |

### 2.1. Password lưu để xác minh người dùng

Password của người dùng không nên được lưu dưới dạng plaintext trong secret manager hay database. Hệ thống xác minh password nên lưu salted password hash được tạo bằng password hashing function chuyên dụng như Argon2id, scrypt hoặc bcrypt theo policy. Secret manager có thể lưu pepper hoặc key bảo vệ bổ sung nếu kiến trúc có sử dụng, nhưng không thay password hashing.

### 2.2. Private key và symmetric key

Private key ký số hoặc symmetric key mã hóa có giá trị cao. Khi có thể, giữ thao tác ký/mã hóa bên trong KMS/HSM để ứng dụng chỉ gọi API với key reference. Không export private key ra file hoặc environment chỉ để tiện dùng nếu không cần.

### 2.3. Certificate không phải private key

Certificate X.509 thường chứa public key, subject/SAN, issuer và thời hạn. Certificate public có thể được phân phối rộng; private key tương ứng phải được bảo vệ. Secret inventory nên phân biệt certificate, private key, serial number, fingerprint và trust bundle để rotation/revocation chính xác.

## 3. Threat model cho secret storage

Tài sản cần bảo vệ gồm raw secret, encryption key, metadata ánh xạ secret tới workload, audit log, backup và quyền quản trị secret manager.

Attacker có thể:

- Đọc source code, container image, build artifact hoặc repository history.
- Truy cập environment variable, process memory, crash dump hoặc debug endpoint.
- Chiếm một workload có quyền đọc secret.
- Lạm dụng service account, CI/CD runner hoặc developer credential.
- Gửi request tới secret manager qua network path không được bảo vệ.
- Khai thác policy wildcard hoặc namespace/path traversal.
- Đọc snapshot/backup hoặc storage backend.
- Lạm dụng quyền admin để export nhiều secret.
- Theo dõi log, trace, metrics hoặc exception có chứa credential.

### 3.1. Trust boundary

~~~mermaid
flowchart LR
    W[Workload identity] -->|Authenticated request| S[Secret manager]
    S -->|Authorization policy| P[Policy engine]
    S -->|Decrypt via key reference| K[KMS / HSM]
    S -->|Secret value over TLS| W
    S --> L[Audit log]
    K --> L
    A[Administrator / CI operator] -->|Privileged access| S
~~~

Các boundary cần xác định:

1. **Workload-to-secret-manager:** caller có được xác minh bằng identity tin cậy không?
2. **Policy boundary:** workload chỉ được đọc secret đúng namespace/path/version và operation không?
3. **Storage boundary:** dữ liệu có được mã hóa và backup bảo vệ không?
4. **Key boundary:** ai có quyền dùng hoặc quản lý encryption key?
5. **Operator boundary:** quyền admin có tách biệt giữa quản lý policy, secret value và audit không?
6. **Runtime boundary:** secret sau khi cấp phát nằm ở memory, file, environment hay sidecar nào?
7. **Observability boundary:** log/trace có thể vô tình sao chép secret sang hệ thống ít tin cậy hơn không?

Không chỉ bảo vệ database của secret manager. Nếu một workload có quyền đọc mọi secret, attacker chiếm workload đó có thể vượt qua lớp mã hóa lưu trữ bằng cách gọi API hợp lệ.

## 4. Kiến trúc lưu trữ và envelope encryption

Secret manager thường mã hóa secret trước khi ghi vào storage backend. Một thiết kế phổ biến dùng **envelope encryption**:

1. Tạo Data Encryption Key (DEK) để mã hóa secret bằng thuật toán AEAD.
2. Dùng Key Encryption Key (KEK) được KMS/HSM bảo vệ để wrap/encrypt DEK.
3. Lưu ciphertext, wrapped DEK, nonce/IV và metadata cần thiết.
4. Khi workload được phép đọc, secret manager yêu cầu KMS unwrap DEK theo policy.
5. Dùng DEK giải mã secret trong memory và trả qua TLS tới caller được xác thực.

~~~mermaid
flowchart TB
    V[Secret plaintext] --> E[AEAD encryption with DEK]
    D[DEK] --> W[Wrap DEK with KEK]
    K[KEK in KMS/HSM] --> W
    E --> C[Ciphertext]
    W --> WD[Wrapped DEK]
    C --> ST[(Encrypted storage)]
    WD --> ST
    ST --> R[Authorized read]
    R --> KMS[KMS unwrap]
    KMS --> D2[DEK in protected memory]
    D2 --> P[Plaintext returned over TLS]
~~~

### 4.1. Vì sao dùng envelope encryption?

- Secret manager có thể mã hóa nhiều secret bằng DEK riêng hoặc theo nhóm.
- KEK không cần rời KMS/HSM.
- Rotation KEK có thể rewrap DEK mà không phải mã hóa lại toàn bộ plaintext.
- KMS policy và audit giúp kiểm soát thao tác unwrap.
- Storage backup chỉ chứa ciphertext và wrapped DEK.

Envelope encryption không ngăn attacker có quyền gọi secret manager lấy plaintext. Nó chủ yếu giảm rủi ro khi storage hoặc backup bị đọc trái phép và tách quyền truy cập dữ liệu khỏi quyền sử dụng master key.

### 4.2. AEAD và metadata

Dùng chế độ authenticated encryption như AES-GCM hoặc ChaCha20-Poly1305 theo thư viện và nền tảng được phê duyệt. Nonce/IV phải được tạo và quản lý đúng yêu cầu thuật toán; không tái sử dụng nonce với cùng key trong các chế độ yêu cầu uniqueness. Có thể đưa secret ID, version, tenant hoặc schema version vào Additional Authenticated Data (AAD) để ngăn ciphertext bị tráo giữa record/context khác nhau.

Không tự thiết kế thuật toán mã hóa, KDF hoặc format key wrapping. Dùng KMS/crypto library đã được duy trì và cấu hình theo chuẩn của nền tảng.

### 4.3. KMS và HSM

- **KMS:** quản lý key, policy, rotation, audit và các thao tác cryptographic qua API.
- **HSM:** phần cứng bảo vệ key và thực hiện thao tác cryptographic trong boundary được kiểm soát.
- **Secret manager:** quản lý secret value, path/version, access policy, lease và delivery.

Ba thành phần có thể tích hợp nhưng không đồng nghĩa. Secret manager dùng KMS để mã hóa storage; HSM có thể bảo vệ root/signing key của KMS hoặc PKI. Chọn mô hình theo assurance, compliance, availability và khả năng vận hành.

## 5. Bootstrap trust: làm sao lấy secret đầu tiên?

Workload cần xác thực với secret manager trước khi đọc secret. Nếu nó phải chứa một static secret dài hạn để lấy secret khác, hệ thống có vấn đề **secret zero**: bí mật bootstrap trở thành điểm yếu có giá trị cao.

Ưu tiên nguồn identity do nền tảng cấp:

- Cloud workload/instance identity.
- Kubernetes projected service account token có audience và TTL giới hạn.
- SPIFFE/SPIRE workload attestation.
- OIDC federation từ CI/CD identity provider.
- mTLS certificate bootstrap được provision qua quy trình tin cậy.
- Hardware-backed identity/attestation khi threat model yêu cầu.

Secret manager xác minh issuer, subject, audience, attestation và policy trước khi tạo session hoặc cấp secret.

### 5.1. Kubernetes workload identity

Kubernetes service account token có thể được project vào pod với audience và expiration phù hợp. Secret manager cần kiểm tra issuer/audience và thông tin workload theo trust configuration. Tránh dùng token service account mặc định sống lâu hoặc mount vào mọi container khi không cần.

RBAC của Kubernetes cần giới hạn ai có thể tạo pod dùng service account nhạy cảm, đọc secret object, exec vào pod hoặc sửa workload spec. Người có quyền tạo pod trong namespace có thể có khả năng sử dụng service account của pod đó; RBAC cần tính đến đường gián tiếp này.

### 5.2. CI/CD federation

CI runner có thể nhận OIDC identity assertion từ nền tảng pipeline và đổi lấy credential ngắn hạn. Trust policy nên ràng buộc:

- Issuer chính xác.
- Subject/repository/project cụ thể.
- Branch, tag, environment hoặc workflow được phép.
- Audience dành cho secret manager hoặc STS.
- Thời hạn assertion.
- Quyền theo từng deployment environment.

Không cho mọi workflow trong tổ chức quyền đọc production secrets chỉ vì chúng dùng cùng issuer. Một pull request từ fork hoặc branch không tin cậy không được nhận credential triển khai production.

### 5.3. Bootstrap fallback

Nếu nền tảng chưa hỗ trợ workload identity, bootstrap secret phải:

- Được cấp riêng cho workload/environment.
- Có quyền tối thiểu, TTL/rotation và revoke.
- Lưu trong secret store hoặc cơ chế provision được kiểm soát.
- Không nằm trong source, image hay artifact.
- Có owner và kế hoạch chuyển sang federation/attestation.

Không chia sẻ một bootstrap key cho toàn bộ cluster hoặc mọi developer.

## 6. Authentication và authorization khi đọc secret

Secret manager cần xác minh caller và kiểm tra policy trước khi trả plaintext.

### 6.1. Authentication

Caller có thể xác thực bằng:

- Workload identity token.
- mTLS client certificate.
- Cloud instance identity.
- OIDC/JWT assertion.
- Human identity thông qua SSO/MFA cho thao tác quản trị.

Không tin header X-Service-Name hoặc tên pod do caller tự gửi làm danh tính. Identity phải được xác minh bằng issuer, signature, certificate chain hoặc attestation đã cấu hình.

### 6.2. Authorization

Policy nên ràng buộc:

- Principal/workload identity.
- Secret path hoặc resource ID.
- Namespace, tenant và environment.
- Operation: read, create, update, delete, rotate, list metadata.
- Version hoặc version stage.
- TTL, lease hoặc điều kiện theo thời gian.
- Network/device/attestation condition khi cần.

Ví dụ policy minh họa:

~~~text
principal: spiffe://prod.example.org/ns/billing/sa/invoice-api
allow:
  - secret: kv/prod/billing/database
    actions: [read]
  - secret: kv/prod/billing/payment-client
    actions: [read]
deny:
  - secret: kv/prod/payroll/*
    actions: [read, write, list]
  - secret: kv/prod/platform/root/*
    actions: [all]
~~~

Policy thực tế cần cú pháp và semantics đúng với sản phẩm; ví dụ trên chỉ thể hiện nguyên tắc. Không dùng wildcard rộng như kv/prod/* cho một service nếu nó chỉ cần một vài secret.

### 6.3. Tách quyền quản trị

Nên tách các vai trò:

- Secret consumer: chỉ đọc secret cụ thể.
- Secret owner: đề xuất/tạo/cập nhật secret trong phạm vi sở hữu.
- Security administrator: quản lý policy và trust configuration.
- KMS administrator: quản lý key lifecycle, không nhất thiết đọc secret plaintext.
- Auditor: đọc audit metadata, không đọc secret value.
- Break-glass operator: quyền khẩn cấp có approval, TTL và hậu kiểm.

Tách nhiệm vụ giúp giảm nguy cơ một tài khoản bị chiếm có thể vừa sửa policy, vừa đọc secret, vừa xóa audit.

## 7. Static secret và dynamic secret

### 7.1. Static secret

Static secret được tạo trước và tồn tại cho tới khi rotate hoặc revoke, ví dụ password của một database user cố định. Secret manager lưu version và phân phối giá trị cho consumer.

Ưu điểm:

- Dễ tích hợp với hệ thống cũ.
- Dễ hiểu và có thể dùng khi upstream không hỗ trợ cấp credential động.

Hạn chế:

- Secret tồn tại lâu và có thể bị sao chép.
- Rotation cần phối hợp consumer và service nhận credential.
- Nhiều workload có thể dùng chung secret, khó xác định nguồn lạm dụng.

### 7.2. Dynamic secret

Dynamic secret được tạo theo yêu cầu, thường gắn với lease và TTL. Ví dụ secret manager tạo database user riêng cho một service instance, cấp quyền chỉ đọc một schema và tự động revoke khi lease hết hạn.

Lợi ích:

- Credential có thời hạn và scope cụ thể.
- Mỗi workload/session có thể có credential riêng.
- Thu hồi theo lease, giảm chia sẻ bí mật.
- Audit có thể ánh xạ credential tới request/workload.

Trade-off:

- Secret manager và backend phải sẵn sàng khi cấp/renew.
- Hệ thống cần xử lý lease renewal, expiration và connection pool.
- Nếu backend không hỗ trợ tạo/revoke credential động, cần adapter hoặc quy trình khác.

### 7.3. Lease lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Issued
    Issued --> Active: Consumer receives secret
    Active --> Renewed: Valid renewal before expiry
    Renewed --> Active
    Active --> Revoked: Explicit revoke
    Active --> Expired: TTL reached
    Revoked --> [*]
    Expired --> [*]
~~~

Lease record thường có lease ID, principal, secret reference, issued time, expiry, renewal limit và revoke status. Không coi lease ID là secret value; nhưng nó vẫn có thể là metadata nhạy cảm cần hạn chế log.

## 8. Rotation và versioning không gây downtime

Rotation là thay credential cũ bằng credential mới và đảm bảo mọi consumer chuyển sang dùng credential mới trước khi credential cũ bị vô hiệu hóa.

### 8.1. Rotation theo hai pha

1. **Prepare:** tạo secret version mới hoặc credential mới; cho phép upstream chấp nhận cả cũ và mới trong overlap window.
2. **Deploy:** consumer đọc version mới, cập nhật connection/client và xác nhận health.
3. **Verify:** quan sát traffic, authentication failure và consumer adoption.
4. **Retire:** revoke credential cũ sau khi mọi consumer đã chuyển và rollback window kết thúc.
5. **Audit:** ghi nhận owner, version, thời điểm và kết quả rotation.

Không rotate secret bằng cách ghi đè một giá trị rồi lập tức revoke giá trị cũ nếu còn consumer đang chạy. Với database password, có thể tạo user mới song song, chuyển workload, rồi disable user cũ.

### 8.2. Secret version

Secret manager nên hỗ trợ version hoặc immutable revision. Consumer có thể tham chiếu:

- Latest/current: tiện nhưng cần refresh và xử lý thay đổi.
- Version cố định: triển khai tái lập được nhưng cần quy trình update.
- Version stage như pending/current/previous: hỗ trợ rotation và rollback có kiểm soát.

Không để ứng dụng vô tình dùng version cũ mãi vì cache vô hạn. Cũng không tự động lấy latest cho mọi request nếu thay đổi secret cần rollout có kiểm thử.

### 8.3. Rotation các loại key

- **Database password:** tạo credential mới, cập nhật consumer, xác nhận connection mới rồi revoke cũ.
- **API key:** hỗ trợ hai key active ngắn hạn, chuyển consumer và tắt key cũ.
- **HMAC signing key:** hỗ trợ key ID và overlap verify; signer chuyển sang key mới, verifier chấp nhận key cũ trong thời gian cần thiết.
- **JWT signing key:** publish JWKS key mới trước khi ký bằng nó; giữ public key cũ cho đến khi token cũ hết hạn hoặc bị revoke.
- **TLS certificate:** provision certificate mới, cập nhật trust/connection, sau đó revoke hoặc để certificate cũ hết hạn theo policy.
- **Encryption KEK:** dùng KMS rewrap DEK theo kế hoạch; không cần đưa plaintext secret ra ngoài chỉ để rotate KEK.

Rotation không phải lúc nào cũng tự động. Cần phân biệt key rotation với secret value rotation và certificate renewal; chúng có dependency khác nhau.

## 9. Revocation, expiration và emergency response

Expiration là hết hạn theo thời gian; revocation là vô hiệu hóa trước expiry. Secret manager cần có đường thu hồi cho cả secret tĩnh, dynamic lease, session và workload identity.

Khi revoke:

- Từ chối lần đọc/cấp mới tiếp theo.
- Thu hồi lease hoặc credential ở upstream nếu hỗ trợ.
- Invalidate cache và refresh token/connection theo policy.
- Chặn workload identity bị compromise khỏi việc xin secret mới.
- Ghi audit và thông báo cho owner/incident response.

Secret manager không thể tự xóa mọi bản sao plaintext đã được cấp cho consumer. Một service có thể đang giữ secret trong memory hoặc connection pool. Vì vậy, emergency response phải phối hợp secret manager, upstream system, workload platform và application.

### 9.1. Khi secret bị lộ

1. Xác định secret ID/version, principal, workload, thời điểm và phạm vi có thể bị truy cập.
2. Chặn nguồn truy cập hoặc disable workload identity nếu bị compromise.
3. Revoke secret/lease ở secret manager và hệ thống đích.
4. Tạo credential mới từ nguồn tin cậy; rotate mọi credential downstream có thể bị lộ.
5. Cập nhật consumer và xác minh health.
6. Kiểm tra audit, database access, API activity, CI/CD logs, image và repository history.
7. Xóa secret khỏi log/artifact có thể xóa an toàn; lưu evidence phục vụ điều tra theo quy trình.
8. Tìm nguyên nhân gốc và bổ sung policy/test để tránh tái diễn.

Không chỉ xóa secret khỏi source code rồi cho rằng đã khắc phục. Git history, build artifact, container registry, cache và log có thể vẫn giữ bản cũ; credential phải được rotate/revoke.

## 10. Đưa secret vào workload

Có nhiều cách phân phối secret. Chọn theo runtime, threat model, khả năng refresh và mức độ tích hợp.

| Cách phân phối | Ưu điểm | Rủi ro/cân nhắc |
| --- | --- | --- |
| SDK/API trực tiếp | Workload tự xác thực và lấy secret đúng lúc cần | Secret nằm trong memory; code phải xử lý retry/cache/logging |
| Agent/sidecar | Tách logic auth/refresh khỏi ứng dụng; có thể ghi file vào tmpfs | Thêm process/network boundary; file permission và lifecycle |
| CSI/volume mount | Secret xuất hiện như file, dễ tích hợp với app đọc file | Cần kiểm soát mount, node, file permission và rotation propagation |
| Environment variable | Dễ tích hợp với app cũ | Có thể lộ qua process inspection, diagnostics, crash dump hoặc log |
| Kubernetes Secret volume | Tích hợp native với pod | Cần encryption at rest, RBAC, node security và mount scope |
| Build-time injection | Dễ đóng gói | Rủi ro cao: secret có thể nằm trong image/layer/artifact |

### 10.1. Environment variable

Environment variable không tự động là sai trong mọi môi trường, nhưng thường khó rotate và có thể bị lộ qua process diagnostics, child process, crash dump, debug tooling hoặc cấu hình logging. Không đặt secret trong build arguments hoặc Docker image layer. Nếu phải dùng environment variable cho legacy app, giới hạn process access, không dump environment và có rotation/restart strategy.

### 10.2. File mount và tmpfs

Mount secret dưới dạng file có thể giảm một số đường rò rỉ so với environment variable, nhất là khi dùng tmpfs và file permission chặt. Tuy nhiên, process vẫn có thể đọc file nếu có quyền; node/root hoặc container escape vẫn có thể truy cập. File update semantics cũng cần được xử lý: ứng dụng phải reload an toàn khi nội dung thay đổi.

### 10.3. Kubernetes Secret

Kubernetes Secret object thường được encode base64 trong manifest/API representation; base64 không phải encryption. Cần:

- Bật encryption at rest cho etcd theo cấu hình cluster.
- Giới hạn RBAC đọc/list/watch secret.
- Hạn chế quyền tạo pod dùng service account có quyền đọc secret.
- Chỉ mount secret vào container cần dùng.
- Tránh đưa secret vào command-line argument hoặc log.
- Bảo vệ etcd backup, node, kubelet và control plane.
- Cân nhắc external secret manager/CSI driver với workload identity.

External secret operator/CSI driver cũng có quyền truy cập secret; phải review controller identity, namespace scope, sync behavior và cách xóa secret khỏi Kubernetes khi nguồn bị revoke.

## 11. Cache và sử dụng secret trong runtime

Ứng dụng thường cache secret để giảm latency và tránh gọi secret manager trên mọi request. Cache cần có thời hạn, version và invalidation policy.

### 11.1. Cache policy

- Cache theo secret ID, version và workload identity; không dùng một biến chung cho nhiều tenant.
- Đặt TTL phù hợp với rotation/revocation SLA.
- Không cache vô thời hạn.
- Dùng single-flight để tránh nhiều thread đồng thời fetch cùng secret.
- Refresh trước expiry với jitter nếu secret có lease.
- Khi nhận revoke/rotation event, invalidate cache nếu hệ thống hỗ trợ.
- Nếu secret manager unavailable, chỉ dùng cache còn hiệu lực theo policy; không kéo dài TTL tùy tiện.

### 11.2. Memory hygiene

Java/JVM không bảo đảm xóa sạch mọi bản sao chuỗi bí mật ngay khi ứng dụng không dùng nữa. Hạn chế lifetime, số bản sao và phạm vi truy cập. Không log secret, không đưa vào exception message, tracing attribute, metrics label hoặc thread dump có thể chia sẻ rộng.

Khi có thể, dùng API cryptographic của KMS/HSM để thao tác bằng key reference thay vì tải private key plaintext vào heap. Với password hoặc token cần dùng trong request, giữ trong memory ngắn nhất có thể và không serialize vào persistent cache.

### 11.3. Connection pool

Database credential rotation có thể không ảnh hưởng connection đã mở; pool tiếp tục dùng connection cũ trong khi connection mới thất bại. Rotation plan phải tính:

- Thời điểm pool tạo connection mới.
- Cách refresh credential và tạo pool/client mới.
- Drain connection cũ sau khi health check đạt.
- Revoke user cũ sau khi không còn connection hợp lệ.
- Retry/backoff để tránh tạo connection storm.

Không chỉ thay giá trị secret trong cache mà quên connection pool đang giữ authentication state cũ.

## 12. Java/Spring: đọc secret qua abstraction

Ứng dụng nên phụ thuộc vào một interface cung cấp secret đã được cấp quyền, còn implementation cụ thể tích hợp với Vault, cloud secret manager hoặc nền tảng nội bộ. Không hardcode secret value hoặc tự viết encryption protocol trong business code.

~~~java
public interface SecretProvider {
    SecretValue read(SecretReference reference);
}

public record SecretReference(
    String name,
    String version,
    String purpose
) {}

public record SecretValue(
    char[] value,
    Instant expiresAt,
    String version
) {}

public final class PaymentClientFactory {
    private final SecretProvider secrets;
    private final Clock clock;

    public PaymentClientFactory(SecretProvider secrets, Clock clock) {
        this.secrets = secrets;
        this.clock = clock;
    }

    public PaymentClient createClient() {
        SecretValue credential = secrets.read(
            new SecretReference(
                "prod/billing/payment-client",
                "current",
                "outbound-payment-api"
            )
        );

        if (credential.expiresAt() != null &&
                !clock.instant().isBefore(credential.expiresAt())) {
            throw new IllegalStateException("Credential is expired");
        }

        try {
            return PaymentClient.connectWithCredential(credential.value());
        } finally {
            Arrays.fill(credential.value(), '\0');
        }
    }
}
~~~

Đây là pseudocode. char[] có thể được ghi đè bởi ứng dụng sau khi dùng, nhưng không bảo đảm xóa mọi bản sao đã được tạo bởi thư viện, JVM hoặc client. Factory thực tế cần quản lý lifecycle của client, refresh, connection pool và credential version. Không tạo client mới cho từng request nếu thư viện cần connection pooling.

### 12.1. Workload identity trước khi đọc secret

~~~java
public final class VaultSecretProvider implements SecretProvider {
    private final WorkloadIdentity identity;
    private final SecretManagerClient client;

    @Override
    public SecretValue read(SecretReference reference) {
        WorkloadAssertion assertion = identity.createAssertion(
            "secret-manager"
        );

        SecretManagerSession session = client.authenticate(assertion);
        AccessDecision decision = session.authorize(
            reference.name(),
            "read"
        );
        if (!decision.allowed()) {
            throw new SecurityException("Secret access denied");
        }

        return session.read(reference);
    }
}
~~~

Đây cũng là pseudocode. Trong production, SDK chính thức thường đã xử lý authentication, TLS, token renewal, retry và policy error. Không gửi assertion tới endpoint do input chọn; audience và issuer phải được cấu hình. Secret manager phải tự thực thi authorization server-side; không chỉ dựa vào kiểm tra ở client.

### 12.2. Cấu hình Spring

Spring Boot có thể tích hợp secret manager thông qua config import, SDK hoặc provider chuyên dụng. Cấu hình minh họa nên chỉ chứa endpoint/secret reference và identity mechanism, không chứa raw credential:

~~~yaml
app:
  credentials:
    payment:
      secret-reference: prod/billing/payment-client
      refresh-before: 2m
      max-cache-age: 5m
~~~

Tên thuộc tính và cách bind tùy ứng dụng. Không đưa secret value vào YAML đã commit. Bảo đảm config dump, Actuator endpoints, startup logs và exception không in credential. Chỉ expose health/metrics cần thiết; không bật endpoint env/config cho người dùng không được phép.

## 13. Audit, monitoring và governance

Secret manager cần ghi nhận metadata đủ để điều tra mà không ghi plaintext.

| Event | Audit metadata |
| --- | --- |
| Secret read | Principal, secret reference, version, time, source, outcome |
| Secret write/update | Actor, owner, version, change reference, approval |
| Secret rotation | Old/new version reference, rotation job, result |
| Lease issue/renew/revoke | Lease ID, principal, TTL, backend role, result |
| Policy change | Actor, policy version, diff/reference, approval |
| KMS unwrap/sign/decrypt | Key ID, caller, operation, context, result |
| Failed access | Principal, requested path, reason code, source |
| Break-glass | Operator, ticket/incident, approval, expiry, actions |

Không ghi secret plaintext, password, API key, access token, private key hoặc request body nhạy cảm. Secret reference cũng có thể tiết lộ kiến trúc; áp dụng phân quyền audit và pseudonymization phù hợp.

### 13.1. Metrics và cảnh báo

- Số lượt đọc secret theo principal/path/environment.
- Access denied và enumeration/list attempts.
- Secret/lease sắp hết hạn, renewal failure và rotation lag.
- Secret manager/KMS latency, error và availability.
- Số workload có quyền đọc production secret.
- Secret không có owner hoặc không được sử dụng trong thời gian dài.
- Access bất thường theo thời gian, region, workload version hoặc environment.
- Policy wildcard, admin grant hoặc break-glass usage.
- Secret xuất hiện trong repository, image, log hoặc artifact scan.

Alert cần có ngữ cảnh và rate threshold để tránh false positive. Không đưa raw secret vào alert payload hoặc ticket.

## 14. Backup, replication và disaster recovery

Secret manager là dependency quan trọng; mất service có thể làm workload không khởi động, không refresh credential hoặc không thể xử lý rotation.

Thiết kế cần:

- Replication theo topology và consistency model phù hợp.
- Backup ciphertext, wrapped DEK, metadata, policy và audit theo yêu cầu.
- Bảo vệ backup bằng key management và access control độc lập.
- Kiểm thử restore định kỳ trong môi trường cô lập.
- Có quy trình khôi phục KMS/HSM key hoặc key material cần thiết.
- Giới hạn quyền export/restore để một operator không thể vừa lấy backup vừa mở khóa mọi secret.
- Xác định RTO/RPO và hành vi ứng dụng khi secret manager tạm unavailable.

Backup ciphertext không đủ nếu mất KEK hoặc metadata cần để unwrap. Ngược lại, backup cả secret plaintext và key cùng một nơi làm mất lợi ích của envelope encryption. Recovery plan cần thử nghiệm toàn bộ chuỗi.

### 14.1. Fail-open hay fail-closed?

Với secret mới chưa từng xác minh hoặc secret đã hết lease, mặc định không cấp quyền chỉ vì secret manager/KMS đang lỗi. Ứng dụng có thể tiếp tục dùng secret hiện tại nếu còn hiệu lực và policy cho phép. Không kéo dài lease vô hạn hoặc dùng credential hết hạn để che outage.

Một số workload có thể cần degraded mode được phê duyệt, ví dụ chỉ đọc cache không nhạy cảm trong thời gian ngắn. Phải định nghĩa trước loại thao tác, TTL tối đa, audit và điều kiện quay lại normal mode.

## 15. Incident response khi secret bị lộ

Một playbook thực tế cần phối hợp nhiều lớp:

1. **Triage:** xác định secret, version, principal, workload, environment, quyền và thời điểm.
2. **Contain:** chặn workload/session bị compromise; disable identity hoặc policy path bị lạm dụng.
3. **Revoke:** thu hồi secret/lease ở secret manager và credential ở upstream.
4. **Rotate:** cấp credential mới và cập nhật consumer theo thứ tự an toàn.
5. **Verify:** kiểm tra request thành công bằng credential mới, credential cũ bị từ chối và service health ổn định.
6. **Hunt:** tìm secret trong source history, image, CI artifact, logs, traces, dumps và backup.
7. **Audit:** xem ai đọc secret, có export/list bất thường hay policy change không.
8. **Recover:** khởi tạo lại workload sạch, cập nhật identity/policy và theo dõi.
9. **Learn:** bổ sung scan, test, owner, rotation automation và giảm quyền.

Nếu private key hoặc KEK bị compromise, phạm vi xử lý rộng hơn một secret value: cần đánh giá dữ liệu đã mã hóa/ký, certificate/token đã phát hành, key version và trust bundle. Có thể cần rotate key hierarchy hoặc re-encrypt/re-sign theo incident plan.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cải thiện |
| --- | --- | --- |
| Secret trong source code/Git | Lộ qua history, fork và clone | Secret manager, scan và rotate ngay khi phát hiện |
| Secret trong container image | Mọi bản image mang credential | Runtime injection bằng workload identity |
| Một secret dùng chung nhiều service | Blast radius lớn, khó audit | Secret riêng theo principal/environment |
| Policy wildcard đọc toàn bộ path | Workload bị compromise lấy mọi secret | Least privilege theo path/version/action |
| Bootstrap secret dài hạn | Secret zero trở thành root credential | Federation/attestation và bootstrap rotation |
| Base64 Kubernetes Secret bị coi là encryption | Secret có thể đọc từ API/etcd backup | Encryption at rest, RBAC, external manager |
| Log config hoặc environment | Secret xuất hiện trong log/traces | Redaction, allowlist config và kiểm thử |
| Rotation ghi đè rồi revoke ngay | Consumer cũ mất kết nối | Two-phase rotation và overlap window |
| Cache secret vô thời hạn | Credential revoked vẫn được dùng | TTL, version và invalidation |
| Không revoke upstream credential | Secret manager chặn đọc mới nhưng credential cũ vẫn hoạt động | Revoke ở hệ thống đích |
| KMS admin đồng thời secret consumer | Một tài khoản có quyền quá lớn | Separation of duties |
| Không backup key metadata | Không thể khôi phục ciphertext | Recovery test cho toàn bộ key hierarchy |
| Secret trong command-line argument | Có thể lộ qua process list/diagnostics | File/SDK/secure injection |
| Lưu password người dùng plaintext | Database compromise lộ password trực tiếp | Argon2id/scrypt/bcrypt với salt |
| Không có owner/expiry | Secret tồn tại mãi và bị quên | Inventory, owner, review và lifecycle policy |
| Debug endpoint hiển thị config | Lộ secret qua Actuator/admin endpoint | Disable/secure endpoint và redaction |

## 17. Ma trận kiểm thử secret manager

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Workload identity hợp lệ đọc secret được cấp | Cho phép và ghi audit metadata |
| Workload tự khai principal khác | Không được cấp danh tính đó |
| Audience/issuer của bootstrap assertion sai | Từ chối authentication |
| Workload đọc secret ngoài path policy | Access denied |
| Workload list toàn bộ namespace | Từ chối nếu không có quyền list |
| Workload ghi/rotate secret chỉ được read | Access denied |
| Developer environment đọc production secret | Từ chối theo environment boundary |
| Secret storage snapshot bị đọc | Chỉ có ciphertext/wrapped DEK, không có plaintext |
| KMS unwrap từ principal không được phép | Từ chối và audit |
| Secret ciphertext bị sửa | AEAD authentication thất bại |
| Ciphertext bị tráo sang secret ID/version khác | AAD/context validation từ chối |
| Dynamic credential hết lease | Upstream credential bị revoke và không được dùng mới |
| Lease renewal vượt giới hạn | Từ chối |
| Secret rotation có consumer đang chạy | Consumer chuyển sang version mới trước khi version cũ bị revoke |
| Một consumer không refresh | Alert/rotation health check phát hiện |
| Secret manager unavailable | Không cấp secret mới; cache còn hiệu lực chỉ dùng theo policy |
| Cache chứa secret đã revoke | Invalidation/TTL ngăn tiếp tục dùng quá SLA |
| Secret xuất hiện trong startup log | Redaction test thất bại |
| Secret xuất hiện trong environment dump | Diagnostic policy chặn hoặc redacts |
| Kubernetes Secret đọc từ namespace khác | RBAC từ chối |
| User có quyền tạo pod dùng privileged service account | RBAC review phát hiện indirect secret access |
| CI workflow từ fork xin production secret | Federation trust policy từ chối |
| Break-glass được sử dụng | Approval, TTL, audit và hậu kiểm đầy đủ |
| Backup restore | Khôi phục được ciphertext, metadata, policy và key hierarchy trong RTO/RPO |
| Git/image/log scan tìm credential đã rotate | Credential cũ bị revoke; finding được xử lý |
| Secret owner rời tổ chức | Ownership chuyển giao và access được review |

### Tình huống thực hành

Một hệ thống có 40 service cùng dùng một database password được lưu trong file cấu hình chung. File nằm trong image registry private; một pipeline CI có quyền pull mọi image. Secret manager đã được triển khai nhưng tất cả service đều có policy đọc `prod/*`. Password được cache vô thời hạn. Khi phát hiện image bị tải bởi tài khoản CI bị chiếm, nhóm chỉ đổi password ở database mà không cập nhật connection pool đang chạy.

**Yêu cầu:** thiết kế lại storage và rotation.

**Hướng phân tích:**

1. Tách database identity/credential theo service hoặc workload role; cấp quyền đúng schema/operation.
2. Xác thực workload bằng platform identity hoặc federation; bỏ secret bootstrap dùng chung nếu có thể.
3. Secret manager policy chỉ cho mỗi principal đọc secret path cụ thể; không cấp `prod/*`.
4. Mã hóa storage bằng envelope encryption với KEK trong KMS/HSM; giới hạn quyền unwrap và audit.
5. Ưu tiên dynamic database credential có lease nếu database và adapter hỗ trợ.
6. Nếu dùng static password, tạo version mới và user/credential song song; rollout consumer và pool, kiểm tra health rồi revoke credential cũ.
7. Cache theo version với TTL; xử lý refresh và invalidation, không cache vô hạn.
8. Revoke password cũ tại database, kiểm tra CI/image/log/history, rotate các secret khác có thể bị lộ và điều tra audit.

## 18. Câu hỏi tự kiểm tra

1. **Secret manager làm nhiệm vụ gì?** Lưu, kiểm soát truy cập, cấp phát, version, rotation, revocation và audit bí mật.
2. **Secret manager có thay identity provider không?** Không. Nó phải xác minh workload/user bằng một nguồn identity tin cậy.
3. **Envelope encryption hoạt động thế nào?** DEK mã hóa secret; KEK trong KMS/HSM wrap DEK; storage giữ ciphertext và wrapped DEK.
4. **KMS và secret manager khác nhau thế nào?** KMS quản lý cryptographic key/operation; secret manager quản lý secret value, policy, lease và delivery.
5. **Vì sao workload identity giúp giải quyết secret zero?** Workload có thể chứng minh identity với nền tảng để lấy secret đầu tiên mà không cần một shared static secret dài hạn.
6. **Dynamic secret có lợi ích gì?** Credential riêng, TTL/lease rõ và có thể revoke theo workload/session.
7. **Vì sao rotation cần overlap window?** Consumer đang chạy cần thời gian chuyển sang credential mới trước khi credential cũ bị vô hiệu hóa.
8. **Kubernetes Secret base64 có được mã hóa không?** Base64 chỉ là encoding; cần encryption at rest và RBAC phù hợp.
9. **Revocation ở secret manager có xóa mọi bản plaintext đã cấp không?** Không. Phải phối hợp revoke ở upstream, invalidate cache và xử lý credential trong runtime.
10. **Có nên cache secret vô thời hạn để tăng availability không?** Không. Cache phải theo TTL, version và revocation SLA; chỉ dùng cache còn hiệu lực theo policy.

**Ghi nhớ:** Secret manager chỉ là một mắt xích trong vòng đời credential. Xác minh workload identity trước khi cấp secret, giới hạn quyền theo principal/path/action, mã hóa storage bằng envelope encryption và bảo vệ KEK trong KMS/HSM. Ưu tiên dynamic credential có lease, rotation hai pha, cache có TTL, audit không chứa plaintext và playbook revoke ở cả secret manager lẫn hệ thống đích. Đừng để secret bootstrap, log, image hoặc cache trở thành bản sao dài hạn ngoài kiểm soát.
