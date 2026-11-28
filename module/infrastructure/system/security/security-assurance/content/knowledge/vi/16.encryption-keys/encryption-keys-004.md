# Key management: quản lý vòng đời khóa mật mã có thể kiểm chứng

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **key management** và vai trò của khóa mật mã trong bảo vệ tính bí mật, toàn vẹn, xác thực và khả năng khôi phục dữ liệu.
2. Phân biệt khóa đối xứng/bất đối xứng, **Data Encryption Key (DEK), Key Encryption Key (KEK), root key, wrapping key, signing key, TLS private key** và credential liên quan.
3. Mô tả vòng đời khóa: thiết kế, tạo, đăng ký, lưu trữ, phân phối, sử dụng, giám sát, luân chuyển, thu hồi, lưu trữ, khôi phục và hủy.
4. Thiết kế kiến trúc quản lý khóa với **KMS/HSM, envelope encryption, key hierarchy, access policy, separation of duties và backup/recovery**.
5. Đánh giá rủi ro lộ khóa, quyền giải mã quá rộng, key reuse, hard-coded secrets, mất khóa, rotation không hoàn tất và xóa nhầm khóa.
6. Chuyển mục tiêu bảo mật thành **key inventory, requirements, security controls, test cases và audit evidence** có thể truy vết.
7. Đo hiệu quả vận hành, xử lý key compromise và duy trì **crypto agility, continuous assurance** khi hệ thống hoặc yêu cầu mật mã thay đổi.

Trong module **SECURITY_SECURITY_ASSURANCE**, việc bật encryption không đủ để chứng minh dữ liệu được bảo vệ. Tổ chức cần chứng minh **khóa được tạo đúng, lưu đúng nơi, chỉ đúng chủ thể được sử dụng, được theo dõi và thay đổi theo chính sách, có thể khôi phục khi cần và bị thu hồi/hủy đúng cách khi hết vòng đời**. Key management là một chuỗi kiểm soát xuyên suốt, liên kết risk assessment, kiến trúc, vận hành, kiểm thử, audit và khắc phục.

## 1. Key management là gì?

**Key management (quản lý khóa mật mã)** là tập hợp chính sách, quy trình, vai trò, công nghệ và bằng chứng quản lý **toàn bộ vòng đời của khóa mật mã**. Mục tiêu là bảo đảm khóa có nguồn gốc đáng tin, được bảo vệ phù hợp, chỉ được sử dụng cho mục đích được phép và vẫn đáp ứng yêu cầu khi cần luân chuyển, khôi phục hoặc hủy.

Một hệ thống có thể dùng thuật toán mã hóa mạnh nhưng vẫn thất bại nếu:

- Khóa được lưu trong source code, file cấu hình hoặc log.
- Nhiều ứng dụng dùng chung một khóa không có owner.
- Tài khoản ứng dụng có thể đọc plaintext hoặc yêu cầu giải mã không giới hạn.
- Nhân viên vừa cấp quyền dùng khóa vừa tự phê duyệt/xóa audit evidence.
- Rotation chỉ đổi alias trong KMS nhưng dữ liệu cũ vẫn phụ thuộc khóa cũ.
- Khóa bị xóa trước khi backup cần khôi phục đã được xử lý.
- Không biết khóa nào bảo vệ dữ liệu nào, ở môi trường/account/region nào.

**Nguyên tắc:** Bảo mật khóa không chỉ là giữ bí mật byte của khóa. Nó còn là **kiểm soát ai có thể yêu cầu cryptographic operation, trong ngữ cảnh nào, trên dữ liệu nào, với mục đích nào và có bằng chứng gì**.

### 1.1. Khóa, mật khẩu, token và certificate

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Cryptographic key** | Tham số bí mật hoặc công khai dùng trong thuật toán mật mã | AES key, private/public key pair |
| **Password/PIN** | Bí mật người dùng biết, thường dùng xác thực hoặc mở khóa authenticator | Password đăng nhập |
| **API token/credential** | Bằng chứng cấp quyền truy cập dịch vụ | Access token, client secret |
| **Certificate** | Gắn public key với danh tính/thuộc tính theo hệ thống chứng thực | TLS certificate |
| **Secret** | Giá trị cần bảo vệ, có thể là key, token, password hoặc credential khác | Database password |
| **KMS/HSM** | Dịch vụ/phần cứng hỗ trợ tạo, lưu, kiểm soát và sử dụng khóa | Cloud KMS, Hardware Security Module |

Một **certificate không phải private key**. Certificate thường chứa public key và thông tin xác thực; private key tương ứng phải được bảo vệ riêng. KMS cũng không tự động quản lý mọi loại secret hoặc token của ứng dụng nếu tổ chức chưa tích hợp và thiết kế vòng đời cho chúng.

### 1.2. Key management bảo vệ những mục tiêu nào?

| Mục tiêu | Kịch bản nếu quản lý khóa kém | Yêu cầu cần xem xét |
|---|---|---|
| **Confidentiality** | Attacker có khóa hoặc quyền decrypt dữ liệu | Giới hạn quyền sử dụng/giải mã, bảo vệ key material |
| **Integrity** | Khóa ký bị lộ hoặc thuật toán dùng sai | Bảo vệ signing key, xác minh chữ ký và rotation |
| **Authentication** | Private key chứng thực dịch vụ bị chiếm | Kiểm soát certificate/private-key lifecycle |
| **Availability** | Khóa mất/hủy sai khiến dữ liệu không đọc được | Backup, recovery, key dependency inventory |
| **Accountability** | Không biết ai dùng khóa hoặc xóa audit log | Audit events, identity, policy version, SoD |
| **Resilience** | Một key compromise ảnh hưởng mọi tenant/dataset | Phân vùng khóa, giới hạn blast radius, crypto agility |

### 1.3. Key management không đồng nghĩa encryption

- **Encryption** bảo vệ dữ liệu bằng thuật toán và khóa.
- **Key management** quản lý khả năng tạo, giữ, sử dụng, thay đổi và hủy khóa.
- **Access control** quyết định chủ thể nào được yêu cầu thao tác với khóa.
- **Secret management** quản lý nhiều loại bí mật; có thể tích hợp KMS nhưng phạm vi rộng hơn.
- **Certificate management/PKI** quản lý danh tính, chứng thư, cấp phát và thu hồi.
- **Data protection** còn gồm phân loại, tối thiểu hóa, backup, audit, retention và xóa dữ liệu.

Một control mã hóa chỉ hiệu quả khi **thuật toán, mode, implementation, key management, quyền truy cập và cách kiểm thử** đều phù hợp với mục tiêu.

## 2. Các loại khóa và cấu trúc phân cấp

### 2.1. Khóa đối xứng và bất đối xứng

**Mật mã đối xứng (symmetric cryptography)** sử dụng cùng một khóa bí mật cho các phép toán mã hóa/giải mã hoặc bảo vệ dữ liệu theo thuật toán tương ứng. Nó thường phù hợp với lượng dữ liệu lớn, nhưng cần quản lý việc phân phối và quyền sử dụng khóa.

**Mật mã bất đối xứng (asymmetric cryptography)** sử dụng cặp khóa có quan hệ toán học:

- **Public key** có thể được phân phối để xác minh chữ ký hoặc mã hóa theo giao thức phù hợp.
- **Private key** cần được bảo vệ; việc lộ khóa có thể làm mất khả năng xác thực, ký hoặc giải mã theo mục đích thiết kế.

Không phải mọi public-key operation đều là “mã hóa bằng private key”; **ký số và mã hóa** là những mục đích khác nhau, cần thuật toán và giao thức đúng.

### 2.2. Các vai trò khóa thường gặp

| Loại khóa | Vai trò | Điều cần quản lý |
|---|---|---|
| **DEK (Data Encryption Key)** | Mã hóa dữ liệu hoặc một phạm vi dữ liệu | Scope, key version, bản sao dữ liệu, quyền dùng và rotation |
| **KEK (Key Encryption Key)** | Bọc/mã hóa DEK để bảo vệ DEK | Quyền unwrap, policy, key hierarchy và recovery |
| **Root/master key** | Gốc tin cậy của một phân cấp khóa | Bảo vệ nghiêm ngặt, backup, quorum/dual control và disaster recovery |
| **Wrapping key** | Bảo vệ khóa khác khi lưu hoặc chuyển | Thuật toán wrapping, quyền unwrap và phiên bản |
| **Signing key** | Tạo chữ ký số cho artifact, token hoặc thông điệp | Ai được ký, key custody, timestamp, verification và compromise response |
| **TLS private key** | Chứng minh danh tính endpoint trong TLS | Certificate binding, renewal, deployment, revocation và quyền export |
| **Key agreement key** | Tham gia thiết lập bí mật chung theo giao thức | Parameter, protocol, validation và key derivation |
| **HMAC key** | Tạo/xác minh message authentication code | Phân tách mục đích, key scope và khả năng rotation |

**Không tái sử dụng một khóa cho nhiều mục đích không tương thích.** Một khóa dùng cho encryption không nên mặc định dùng luôn cho signing, HMAC hoặc key wrapping. Việc tách mục đích giảm rủi ro từ một lỗi hoặc compromise lan sang nhiều cơ chế.

### 2.3. Key hierarchy và envelope encryption

Một kiến trúc phổ biến là **envelope encryption**:

1. Hệ thống tạo một DEK cho dữ liệu hoặc phạm vi được thiết kế.
2. DEK mã hóa dữ liệu bằng thuật toán/mode đã được phê duyệt.
3. KMS/HSM dùng KEK để **wrap (bọc) DEK**.
4. Ứng dụng lưu ciphertext và wrapped DEK cùng metadata cần thiết.
5. Khi đọc, ứng dụng có quyền yêu cầu KMS unwrap DEK, sau đó giải mã trong phạm vi cần thiết.

~~~mermaid
flowchart TD
    A["Application / data service"] --> B["Generate or obtain DEK"]
    B --> C["Encrypt data"]
    C --> D[("Ciphertext + wrapped DEK<br/>+ key version metadata")]
    B --> E["KMS/HSM: wrap DEK"]
    E --> F["KEK protected by<br/>KMS/HSM boundary"]
    G["Authorized read path"] --> H["KMS policy decision"]
    H --> I["Unwrap DEK"]
    I --> J["Decrypt within<br/>approved application boundary"]
    D --> J
~~~

Envelope encryption giúp tách **mã hóa dữ liệu lớn** khỏi **quản lý khóa gốc**, hỗ trợ rotation KEK mà không nhất thiết mã hóa lại toàn bộ ciphertext trong mọi thiết kế. Tuy nhiên:

- Ai có quyền yêu cầu KMS unwrap DEK có thể có khả năng đọc dữ liệu.
- Nếu ứng dụng ghi plaintext ra log hoặc memory dump, envelope encryption không ngăn lộ ở những nơi đó.
- Wrapped DEK phải lưu cùng metadata **algorithm, key ID/version, context/AAD** phù hợp.
- Rotation KEK có thể yêu cầu **rewrap DEK**, nhưng không tự động thay DEK hoặc mã hóa lại dữ liệu.
- Cần kiểm tra backup, replicas, cache, export và các bản copy dùng wrapped DEK cũ.

### 2.4. DEK và KEK khác nhau thế nào?

| Thuộc tính | DEK | KEK |
|---|---|---|
| Mục đích | Mã hóa/giải mã dữ liệu | Bọc/giải bọc DEK hoặc khóa khác |
| Nơi dùng | Data service hoặc cryptographic boundary | KMS/HSM hoặc dịch vụ quản lý khóa |
| Phạm vi ảnh hưởng | Dataset/object/record tùy thiết kế | Tất cả DEK phụ thuộc KEK |
| Rotation | Có thể yêu cầu re-encryption hoặc chuyển đổi dữ liệu | Có thể rewrap DEK, nhưng cần kiểm tra metadata và bản sao |
| Rủi ro | Lộ có thể làm lộ dữ liệu tương ứng | Lộ có thể mở rộng ảnh hưởng tới nhiều DEK |

Một KEK có quá nhiều DEK phụ thuộc sẽ tạo **blast radius** lớn. Tổ chức cần phân vùng theo ứng dụng, môi trường, tenant hoặc mức nhạy cảm khi phù hợp, cân bằng giữa vận hành và giới hạn tác động.

## 3. Threat modeling cho key management

### 3.1. Kịch bản rủi ro chính

| Risk scenario | Hậu quả | Câu hỏi assurance |
|---|---|---|
| Private key/DEK bị lộ | Dữ liệu giải mã được hoặc chữ ký giả mạo | Key material có thể export? Ai có thể đọc/unwrap? |
| Quyền KMS quá rộng | Dịch vụ hoặc người dùng decrypt dữ liệu không cần thiết | Policy có scope theo principal, action, resource và context? |
| Hard-coded key trong repo | Key tồn tại trong lịch sử Git, artifact và fork | Có secret scanning, revocation và evidence xử lý toàn bộ copies? |
| Key dùng chung giữa môi trường | Dev/test compromise ảnh hưởng production | Có phân tách key và policy theo môi trường? |
| Key không được rotation | Khóa cũ tồn tại lâu, không phù hợp cryptoperiod | Có trigger, lịch, theo dõi và tiêu chí hoàn tất? |
| Rotation không hoàn tất | Một phần dữ liệu vẫn phụ thuộc key cũ | Có inventory dependency và reconciliation sau rotation? |
| Xóa nhầm KEK | Dữ liệu không thể giải mã/khôi phục | Có approval, backup và restore test trước hủy? |
| Key backup bị mất hoặc lộ | Mất availability hoặc compromise mở rộng | Backup được bảo vệ, tách quyền và kiểm thử phục hồi? |
| KMS/HSM admin sửa policy | Tự mở quyền hoặc làm gián đoạn sử dụng | SoD, change control, audit và independent review? |
| Signing key bị chiếm | Artifact/token/chứng thư giả mạo | Có revoke, trust update, key replacement và incident playbook? |
| Log không ghi key operation | Không truy vết được hành động nhạy cảm | Audit coverage và telemetry health có được kiểm tra? |
| Vendor giữ quyền quản lý khóa | Không rõ trách nhiệm và khả năng kiểm tra | Shared responsibility, contract và evidence scope? |

### 3.2. Tài sản và trust boundaries

Khi threat model, đừng chỉ vẽ KMS. Xác định:

- **Key material:** khóa gốc, DEK, KEK, private keys, backup copies và wrapped keys.
- **Key metadata:** key IDs, aliases, versions, algorithm, purpose, state, dependency và owner.
- **Principals:** application identities, operators, administrators, service accounts, vendor support.
- **Cryptographic operations:** generate, encrypt, decrypt, wrap, unwrap, sign, verify, import, export, disable, schedule deletion.
- **Data stores:** DB, object storage, backup, queue, cache, logs, artifacts và local volumes.
- **Control planes:** KMS policy, HSM admin, cloud IAM, CI/CD, secrets manager và approval workflow.
- **Recovery boundaries:** vùng dự phòng, account khác, offline backup, quorum custodians và quy trình disaster recovery.

~~~mermaid
flowchart LR
    A["Application identity"] -->|"Encrypt / Decrypt request"| K["KMS API"]
    O["Key operator"] -->|"Admin / policy change"| K
    K --> H["HSM / protected key boundary"]
    K --> L[("Key operation audit")]
    A --> D[("Database / object storage")]
    D --> B[("Backup / DR account")]
    V["Vendor support"] -. "Support / delegated access" .-> K
    C["CI/CD and secrets workflow"] --> A
~~~

**Control plane và data plane** cần được đánh giá riêng. KMS có thể bảo vệ key material tốt nhưng một administrator có thể sửa policy cho phép một application identity decrypt quá rộng; hoặc pipeline deploy nhầm identity có quyền unwrap. Bảo vệ phần cứng không thay thế kiểm soát quyền và thay đổi.

### 3.3. Xác định blast radius

Với mỗi key, trả lời:

1. Khóa bảo vệ **dataset, tenant, service, environment hoặc artifact** nào?
2. Có bao nhiêu DEK/key objects phụ thuộc?
3. Những ứng dụng và principal nào có thể yêu cầu cryptographic operations?
4. Nếu bị lộ, attacker có thể **giải mã dữ liệu đã lưu**, dữ liệu tương lai hay giả mạo chữ ký?
5. Nếu bị xóa hoặc disable, dịch vụ nào mất khả năng đọc/ghi hoặc xác minh?
6. Backup/replica nào phụ thuộc phiên bản đó?
7. Có thể **cô lập, revoke, rotate và recover** trong thời gian chấp nhận được không?

Một key ID không có dependency mapping khiến incident response khó xác định phạm vi. Key inventory phải liên kết **khóa → dữ liệu/ứng dụng → quyền → bản sao → owner → evidence**.

## 4. Vòng đời khóa mật mã

Quản lý khóa là một vòng đời, không phải một thao tác “tạo key trong KMS”.

~~~mermaid
stateDiagram-v2
    [*] --> DESIGNED
    DESIGNED --> GENERATED
    GENERATED --> REGISTERED
    REGISTERED --> ACTIVE
    ACTIVE --> ROTATING
    ROTATING --> ACTIVE: New version verified
    ACTIVE --> DISABLED: Suspend / incident
    DISABLED --> ACTIVE: Approved reactivation
    DISABLED --> REVOKED
    ACTIVE --> RETIRED
    RETIRED --> ARCHIVED
    ARCHIVED --> DESTROYED
    REVOKED --> DESTROYED
    DESTROYED --> [*]
~~~

Sơ đồ là mô hình khái niệm. Thực tế có thể có trạng thái **pending import, pending deletion, compromised, recovery-only, decrypt-only, expired, quarantined**. Trạng thái phải có nghĩa rõ trong hệ thống và được phản ánh vào inventory.

### 4.1. Thiết kế trước khi tạo

Mỗi key cần có **mục đích và phạm vi**:

- Dùng để encrypt, decrypt, sign, verify, wrap, unwrap hay key agreement?
- Ai là owner nghiệp vụ, system owner và control owner?
- Thuật toán/mode/độ dài/parameter nào được baseline phê duyệt?
- Key có được export hay phải non-exportable trong HSM/KMS?
- Dữ liệu và bản sao nào phụ thuộc?
- Cryptoperiod, rotation trigger, expiry và revocation conditions là gì?
- Có cần backup/recovery, dual control hoặc quorum?
- Khi compromise hoặc mất khóa, ai quyết định và ứng phó?

Không tạo một key “dùng chung cho toàn nền tảng” nếu không có phân tích blast radius và phê duyệt phù hợp.

### 4.2. Generation — tạo khóa an toàn

Khóa cần được tạo bằng **cryptographically secure random number generator (CSPRNG)** hoặc cơ chế sinh khóa đáng tin trong cryptographic module phù hợp.

Kiểm tra:

- Nguồn entropy và CSPRNG được hỗ trợ/kiểm định theo yêu cầu của tổ chức.
- Key size, algorithm, mode và parameters đáp ứng baseline hiện hành.
- Không dùng **random thường, timestamp, UUID hoặc giá trị dễ đoán** thay cho key generation.
- Không tự chế thuật toán hoặc quy trình “trộn thêm hash” nếu không có thiết kế được đánh giá.
- Key material không xuất hiện trong console output, log, crash dump, source code hoặc ticket.
- Metadata generation ghi được **key ID, algorithm, purpose, owner, thời điểm, version và trạng thái**, không ghi byte bí mật.

Nếu phải import key được tạo ngoài KMS, cần quản lý **nguồn gốc, key ceremony, secure transfer/wrapping, người tham gia và bằng chứng kiểm tra**. Import thành công không tự chứng minh quá trình tạo và chuyển khóa trước đó an toàn.

### 4.3. Registration và inventory

Sau khi tạo/import, đăng ký:

- Key ID/alias, version, purpose và thuật toán.
- Key type, owner, application/system, environment và tenant scope.
- KMS/HSM/account/region, nơi giữ và trạng thái exportability.
- DEK/KEK relationship, data dependencies và wrapped-key metadata.
- Principal được phép thực hiện từng operation.
- Ngày tạo, activation, cryptoperiod, rotation due, expiry và destruction schedule.
- Backup/recovery reference, exception, incident và evidence IDs.

**Key inventory không được lưu raw key material.** Nó là danh mục metadata và quan hệ phụ thuộc; quyền xem inventory cũng cần được quản lý vì nó có thể tiết lộ kiến trúc và phạm vi tài sản.

### 4.4. Storage — bảo vệ khi lưu

Khóa cần được lưu trong boundary phù hợp, ví dụ **KMS/HSM hoặc secrets/key vault** được tổ chức phê duyệt. Tránh:

- Hard-code trong source, Docker image, build artifact hoặc IaC state không được bảo vệ.
- Để private key/DEK trong file chia sẻ, ổ đĩa cá nhân hoặc ticket.
- Đặt key trong cùng vùng quyền với dữ liệu mà không có kiểm soát phân tách phù hợp.
- Dùng key giống nhau cho dev/test/prod mà không có quyết định rủi ro.
- Sao chép raw key qua email/chat hoặc biến log thành nơi lưu key.

Nếu key material phải nằm ngoài HSM/KMS vì kiến trúc, cần **encryption-at-rest, access control, process isolation, memory protection, backup protection và audit** theo threat model; ngoại lệ phải có owner và giới hạn.

### 4.5. Distribution và import/export

Khi phân phối key hoặc wrapped key:

1. Xác minh **bên gửi, bên nhận, mục đích và quyền**.
2. Dùng cơ chế key wrapping hoặc protocol đã được phê duyệt; bảo vệ tính toàn vẹn và chống thay thế.
3. Không truyền raw key qua kênh thông thường hoặc đưa vào client nếu không có kiến trúc phù hợp.
4. Xác minh key ID/version và context tại nơi nhận.
5. Ghi event, người/machine identity, thời điểm và kết quả.
6. Nếu export được phép, ghi **căn cứ, thời hạn, người phê duyệt, nơi nhận và cách xóa bản tạm**.

Đối với private keys cần non-exportable, test phải chứng minh **đường export bị chặn** theo policy, không chỉ dựa vào một checkbox cấu hình.

### 4.6. Usage — sử dụng khóa

Một request encrypt/decrypt/sign cần được đánh giá theo:

- Principal nào yêu cầu, có xác thực đáng tin không?
- Operation có đúng **key purpose, resource, environment và context**?
- Có giới hạn tenant/object/field hoặc phạm vi dữ liệu không?
- Có cần approval hoặc step-up cho thao tác nhạy cảm?
- Có audit event và correlation ID không?
- Kết quả có được xử lý trong vùng tin cậy; plaintext có đi vào log, memory dump hoặc export không?
- Có rate limit, anomaly detection và failure handling phù hợp không?

**Quyền dùng khóa khác quyền đọc raw key material.** Một ứng dụng có thể gọi KMS decrypt mà không bao giờ nhận được KEK. Tuy nhiên, nếu ứng dụng có thể gửi ciphertext tùy ý và nhận plaintext, nó vẫn có khả năng trở thành **decryption oracle**. Cần giới hạn operation theo context và authorization nghiệp vụ.

### 4.7. Rotation — luân chuyển khóa

Rotation là chuyển hoạt động sang **key version mới** theo chính sách hoặc trigger. Không nên coi mọi loại key rotation giống nhau.

Các câu hỏi:

- Rotation **KEK** có thể rewrap DEK hay cần quy trình khác?
- Rotation **DEK** có yêu cầu re-encrypt dữ liệu cũ hay chỉ dùng key mới cho dữ liệu mới?
- Signing key mới có cần cập nhật trust stores, verifier và token validation?
- TLS private key/certificate mới đã được triển khai trên mọi endpoint?
- Backup/replica/export và consumer cũ còn phụ thuộc version nào?
- Có giai đoạn **decrypt old / encrypt new** được phê duyệt không? Khi nào old key ngừng dùng?
- Làm sao chứng minh **không còn workload dùng key cũ** trước khi retire/destroy?

Rotation phải có **migration plan, rollback, monitoring và reconciliation**. Đổi alias sang version mới không tự chuyển dữ liệu hoặc client sang khóa mới.

### 4.8. Disable, revoke và compromise

**Disable** có thể tạm dừng sử dụng; **revoke** làm mất hiệu lực tin cậy/ủy quyền theo ngữ cảnh, ví dụ certificate hoặc signing key; **destroy** loại bỏ key material theo quy trình. Các hành động có ý nghĩa khác nhau.

Khi nghi khóa bị compromise:

1. Xác định key ID/version, mục đích, thời điểm và dấu hiệu.
2. Đánh giá **data/tenant/service/signature** có thể bị ảnh hưởng.
3. Theo playbook được phê duyệt, hạn chế operation, revoke/disable hoặc thay khóa; cân nhắc availability.
4. Phát hành key version mới và cập nhật dependent systems.
5. Đánh giá dữ liệu đã mã hóa có cần re-encrypt, chứng thư/token có cần revoke, chữ ký cũ có cần xem xét không.
6. Kiểm tra audit logs, backup, replicas, exports và các nơi có thể chứa raw/wrapped key.
7. Bảo vệ evidence điều tra, thông báo bên liên quan và ghi finding.
8. Retest, đánh giá residual risk và cập nhật inventory/policy.

Không nên xóa ngay key bị nghi compromise nếu việc đó **phá bằng chứng hoặc làm mất khả năng khôi phục dữ liệu** mà chưa có quyết định incident owner. Nhưng cũng không tiếp tục dùng key bị nghi lộ như bình thường; cần containment theo kế hoạch.

### 4.9. Archive, backup, recovery và destruction

Một key có thể không còn dùng để encrypt dữ liệu mới nhưng vẫn cần **decrypt dữ liệu lưu trữ** trong thời gian được phép. Trạng thái đó cần được giới hạn thành **decrypt-only/archive** theo policy, không giữ quyền sử dụng rộng.

Trước khi hủy:

- Xác minh không còn dataset, backup, replica, archive hoặc artifact cần key.
- Xác minh migration/rewrap/re-encryption đã hoàn tất và được kiểm tra.
- Đánh giá nghĩa vụ giữ, legal hold và khả năng phục hồi.
- Có approval phù hợp, separation of duties và **destruction evidence**.
- Kiểm tra mọi bản backup/escrow hoặc replica có liên quan tới key material.
- Sau hủy, test không còn operation hợp lệ với key và không phá dữ liệu phải giữ.

**Mất khóa** có thể đồng nghĩa mất dữ liệu vĩnh viễn. Vì vậy backup/recovery cần bảo vệ ngang hoặc cao hơn khóa chính, có tách quyền và thử phục hồi thực tế; không coi “backup job succeeded” là bằng chứng có thể khôi phục.

## 5. Cryptoperiod, rotation policy và crypto agility

### 5.1. Cryptoperiod là gì?

**Cryptoperiod** là khoảng thời gian khóa được phép sử dụng theo chính sách và mục đích cụ thể. Nó có thể gồm thời gian được phép **tạo chữ ký/mã hóa** và thời gian được phép **xác minh/giải mã dữ liệu cũ**.

Không có một thời hạn duy nhất đúng cho mọi key. Quyết định phụ thuộc:

- Thuật toán, key size, use case và chuẩn nội bộ/được áp dụng.
- Lượng dữ liệu/operations và khả năng lộ khóa.
- Mức nhạy cảm, phạm vi phụ thuộc và hậu quả compromise.
- Cơ chế bảo vệ, audit, non-exportability và access scope.
- Khả năng chuyển đổi dữ liệu, thiết bị, certificate và consumer.
- Yêu cầu pháp lý, hợp đồng, tiêu chuẩn và khả năng vận hành.

Không tự đặt một con số rotation chung cho tất cả khóa. **Security/crypto owner** cần phê duyệt cryptoperiod theo baseline và risk assessment, rồi có bằng chứng theo dõi.

### 5.2. Trigger rotation

Rotation có thể được kích hoạt bởi:

- Đến hạn cryptoperiod đã phê duyệt.
- Có nghi vấn hoặc xác nhận **key compromise**.
- Nhân sự/vendor có quyền quản lý rời vai trò hoặc quyền bị thay đổi.
- Thay đổi thuật toán, key size, protocol hoặc baseline.
- Thay đổi kiến trúc, tenant, môi trường hoặc mức nhạy cảm dữ liệu.
- Sự cố vận hành, lỗi HSM/KMS hoặc mất tính toàn vẹn của key inventory.
- Yêu cầu từ auditor, khách hàng, hợp đồng hoặc quy định áp dụng.

### 5.3. Rotation không phải re-encryption

| Hoạt động | Ý nghĩa | Kết quả cần xác minh |
|---|---|---|
| **KEK rotation** | Thay key bọc DEK | DEK được rewrap hoặc xử lý theo thiết kế; old KEK hết dependency |
| **DEK rotation** | Thay khóa mã hóa dữ liệu | Dữ liệu cần chuyển được re-encrypt hoặc quản lý version đúng |
| **Signing key rotation** | Chuyển sang key ký mới | Verifier/trust chain nhận key mới; token/artifact cũ xử lý theo policy |
| **TLS key/certificate renewal** | Thay private key/certificate endpoint | Tất cả endpoint/consumer dùng cert mới; old cert xử lý/revoke phù hợp |
| **Credential rotation** | Thay password/token/secret của service | Workload dùng credential mới; old credential revoke; không còn nơi lưu cũ |

**Ví dụ:** KMS tự động tạo version KEK mới nhưng DEK vẫn được wrap bằng version cũ. Nếu policy cho phép decrypt old key, dữ liệu có thể vẫn đọc được; nhưng chưa thể nói **mọi DEK đã được rewrap** hoặc old key có thể hủy.

### 5.4. Crypto agility

**Crypto agility** là khả năng chuyển đổi thuật toán, tham số, khóa và protocol có kiểm soát khi baseline hoặc rủi ro thay đổi, không phải thay thuật toán tùy ý trong một lần deploy.

Thiết kế hỗ trợ agility:

- Lưu metadata **algorithm/version/key ID** cùng ciphertext hoặc artifact.
- Không hard-code giả định về một key alias hoặc algorithm duy nhất khắp ứng dụng.
- Có inventory những hệ thống và dữ liệu phụ thuộc thuật toán.
- Test khả năng **đọc dữ liệu cũ, ghi dữ liệu mới và migrate** trong giai đoạn chuyển đổi.
- Có plan cho legacy clients, backup, certificate trust và vendor.
- Có thời điểm dừng algorithm/key version cũ và evidence chứng minh không còn sử dụng.

Khi một thuật toán bị suy yếu, tổ chức phải xác định **dữ liệu lưu dài hạn và nguy cơ harvest-now-decrypt-later** nếu phù hợp; việc đổi key hôm nay không tự bảo vệ ciphertext đã bị sao chép trước đó nếu thuật toán hoặc key đã bị lộ.

## 6. KMS và HSM: trách nhiệm và giới hạn

### 6.1. Key Management Service (KMS)

KMS thường cung cấp API/quản lý metadata, policy, version, cryptographic operations và audit integration. Tùy dịch vụ, key material có thể được bảo vệ trong phần cứng chuyên dụng hoặc kiến trúc provider.

Điểm cần kiểm chứng:

- **Key origin:** tạo trong KMS, import hay external key store?
- **Key custody/exportability:** ai kiểm soát material và có thể export không?
- **Policy:** principal, action, resource, context và điều kiện nào được phép?
- **Version/rotation:** tự động hay thủ công; consumer dùng version nào?
- **Audit:** event nào được ghi, retention và nơi lưu?
- **Availability/region:** dependency, failover và giới hạn hoạt động khi dịch vụ lỗi?
- **Recovery/deletion:** backup, key disable/deletion schedule và khả năng khôi phục?
- **Provider responsibility:** phần nào do provider vận hành, phần nào khách hàng cấu hình?

### 6.2. Hardware Security Module (HSM)

**HSM** là thiết bị/phần cứng chuyên dụng bảo vệ key material và thực hiện một số cryptographic operations trong boundary được thiết kế. Nó có thể hỗ trợ non-exportable keys, access controls, audit và quy trình quản trị đặc biệt.

HSM không tự động giải quyết:

- Ai được gọi API để yêu cầu ký/giải mã.
- Ứng dụng có dùng operation cho dữ liệu trái phép không.
- Policy, backup, quorum, operator separation và recovery được vận hành thế nào.
- Log có được gửi và bảo vệ độc lập không.
- Hệ thống tích hợp có lưu plaintext/secret ở nơi khác không.

### 6.3. So sánh KMS và HSM

| Tiêu chí | KMS managed service | HSM |
|---|---|---|
| Mục đích | Quản lý khóa và cryptographic operations qua dịch vụ | Bảo vệ key material và xử lý mật mã trong phần cứng |
| Tích hợp | API, IAM, cloud services | PKCS#11/JCE/provider hoặc giao diện được hỗ trợ |
| Quản trị | Thường có policy, lifecycle và audit do dịch vụ hỗ trợ | Có thể yêu cầu key ceremony, partition, operator/quorum |
| Trách nhiệm | Shared responsibility với provider | Phụ thuộc triển khai, vận hành, vật lý và quản trị |
| Rủi ro | Policy quá rộng, misconfiguration, dependency provider | Quản trị thiết bị, backup, quorum, availability và tích hợp |
| Assurance | Kiểm tra config, identity, operation logs, provider evidence | Kiểm tra firmware/config, ceremony, roles, logs và recovery |

Không có câu trả lời “HSM luôn an toàn hơn KMS” trong mọi kiến trúc. Chọn theo **mục tiêu, threat model, yêu cầu chứng nhận, custody, availability, vận hành và khả năng kiểm chứng**.

## 7. Access control và separation of duties cho khóa

### 7.1. Tách các quyền

Đừng gộp mọi thao tác thành một role KeyAdmin. Cân nhắc phân biệt:

- **Key creator/provisioner:** tạo hoặc import khóa theo workflow.
- **Key administrator:** quản lý metadata, policy và lifecycle.
- **Key user/consumer:** gọi encrypt/decrypt/sign trong scope được phép.
- **Security approver:** phê duyệt thay đổi quyền, rotation hoặc exception theo thẩm quyền.
- **Auditor/assurance reviewer:** đọc evidence và kiểm tra độc lập.
- **Backup/recovery custodian:** tham gia phục hồi theo cơ chế tách quyền/quorum.
- **Incident responder:** có quyền khẩn cấp theo playbook và phải được audit.

Một người có thể kiêm nhiệm khi quy mô hạn chế, nhưng cần đánh giá **toxic combinations**: tự tạo key, tự cấp quyền decrypt, tự sửa policy, tự xóa log và tự xác nhận control đạt.

### 7.2. Least privilege theo cryptographic operation

Quyền nên giới hạn theo:

| Chiều | Ví dụ |
|---|---|
| **Principal** | Application identity cụ thể, không phải mọi account |
| **Operation** | Encrypt được phép nhưng decrypt chỉ ở một service |
| **Key/resource** | Chỉ key ID/version thuộc ứng dụng hoặc tenant |
| **Context** | Environment, encryption context/AAD hoặc request attributes phù hợp |
| **Data scope** | Dataset, object hoặc purpose theo thiết kế |
| **Time** | JIT access, hạn quyền và reapproval |
| **Network/workload** | Trusted workload identity, endpoint và execution context |

Encryption context/AAD có thể ràng buộc ciphertext với metadata như tenant/object ID trong một thiết kế phù hợp; tuy nhiên **không thay authorization**. Attacker có thể lợi dụng ứng dụng có quyền unwrap nhưng không kiểm tra quyền người dùng trên object.

### 7.3. Dual control và M-of-N

Với root key hoặc thao tác ảnh hưởng rộng, tổ chức có thể yêu cầu **hai người độc lập hoặc quorum M-of-N** cho một số bước quản trị/khôi phục.

Kiểm chứng:

- Custodians có danh tính riêng, quyền và trách nhiệm được ghi.
- Quy trình chia sẻ/giữ phần bí mật không làm một người tự khôi phục toàn bộ.
- Điều kiện đủ người, phê duyệt và audit được kiểm tra.
- Backup/custodian thay đổi có quy trình rotation và thu hồi.
- Emergency process có thời hạn và hậu kiểm.

Không nên nhầm **hai tài khoản** với hai người độc lập; một cá nhân có thể kiểm soát nhiều account. SoD cần dựa trên danh tính và miền trách nhiệm theo chính sách.

### 7.4. Kiểm soát KMS policy changes

Thay policy có thể tạo hiệu ứng tương đương cấp quyền giải mã. Một quy trình thay đổi nên:

1. Có change request gắn key ID, mục đích, principal và operations cần thêm/bớt.
2. Phân tích blast radius và quyền hiện tại/kế thừa.
3. Review bởi người có thẩm quyền, độc lập phù hợp.
4. Test policy trong môi trường an toàn hoặc theo phương pháp được phê duyệt.
5. Triển khai theo version/change ID, xác minh effective policy.
6. Test positive/negative cryptographic operations.
7. Theo dõi audit events và rollback khi policy gây lỗi.

## 8. Key inventory và policy có cấu trúc

### 8.1. Key inventory nên chứa gì?

| Nhóm | Metadata cần thiết | Giá trị assurance |
|---|---|---|
| **Identity** | Key ID, alias, version, status | Định danh và tránh nhầm phiên bản |
| **Purpose** | Encrypt/decrypt/sign/wrap/TLS | Ngăn reuse sai mục đích |
| **Cryptography** | Algorithm, mode, size/parameters, module | Kiểm tra baseline |
| **Ownership** | Business/system/control owner | Có người chịu trách nhiệm |
| **Location** | KMS/HSM, account, region, partition | Xác định boundary |
| **Dependencies** | DEKs, datasets, applications, certificates, backups | Blast radius và migration |
| **Access** | Principals, operations, context, approvals | Least privilege và SoD |
| **Lifecycle** | Created, active, rotation due, expiry, retire/destroy | Theo dõi trạng thái |
| **Recovery** | Backup/escrow reference, quorum, restore test | Availability |
| **Assurance** | Policy version, test/evidence IDs, findings | Truy vết và audit |

Không lưu **raw key, seed, private key, recovery share hoặc secret** trong inventory. Dùng tham chiếu có phân quyền và metadata không tiết lộ material.

### 8.2. Ví dụ YAML

Đây là **mẫu giáo dục**, không phải schema chuẩn của một KMS:

~~~yaml
keyRecord:
  id: KEY-PAYMENTS-KEK-PROD
  alias: payments-prod-data-kek
  version: "7"
  status: active
  purpose: wrap-dek

  ownership:
    businessOwner: Payments Data Owner
    systemOwner: Payments Platform Owner
    controlOwner: Cryptographic Controls Lead
    riskOwner: Payments Risk Owner

  cryptography:
    algorithmReference: APPROVED-KEY-WRAPPING-BASELINE
    keyMaterialExportable: false
    protectionBoundary: managed-kms-hsm

  location:
    providerAccount: payments-production
    regionReference: APPROVED-KEY-REGION
    keyStoreReference: payments-prod-kms

  dependencies:
    wrappedKeyInventory: DEK-INVENTORY-PAYMENTS
    datasets:
      - PAYMENT-INSTRUCTIONS
      - REFUND-RECORDS
    applications:
      - payment-api
      - refund-worker
    backups:
      - payment-db-backup

  access:
    allowedPrincipals:
      - payment-api-workload
      - refund-worker-workload
    allowedOperations:
      - wrap
      - unwrap
    policyReference: POLICY-PAYMENTS-KEK
    adminChangeApproval: CRYPTO-CHANGE-APPROVAL

  lifecycle:
    createdAt: "2026-01-15"
    activatedAt: "2026-01-15"
    cryptoperiodReference: CRYPTOPERIOD-PAYMENTS-KEK
    nextReviewReference: KEY-REVIEW-CALENDAR
    rotationPlan: ROTATE-KEK-REWRAP-DEKS
    retirementCriteria: NO-DEPENDENT-WRAPPED-KEYS

  recovery:
    backupReference: KEY-RECOVERY-PROCEDURE
    quorumReference: KEY-CUSTODIAN-POLICY
    lastRestoreTestReference: TEST-KEY-RECOVERY-04

  assurance:
    requirementIds:
      - KEY-01
      - KEY-ACCESS-02
      - KEY-ROTATION-03
      - KEY-RECOVERY-04
    controlIds:
      - CTRL-KMS-LEAST-PRIVILEGE
      - CTRL-KEY-ROTATION
      - CTRL-KEY-RECOVERY
    evidenceIds:
      - EV-KMS-POLICY-REVIEW
      - EV-KEY-OPERATION-AUDIT
    openFindings:
      - FIND-LEGACY-DEK-DEPENDENCY
~~~

Các trường tham chiếu như TEST-KEY-RECOVERY-04 không chứng minh test đã chạy. Muốn dùng làm assurance evidence phải có **kết quả, ngày, môi trường, key version, người thực hiện, expected/actual và giới hạn**.

### 8.3. Trạng thái key phải có nghĩa vận hành

| Trạng thái | Diễn giải | Điều cần kiểm tra |
|---|---|---|
| **PLANNED** | Đã thiết kế nhưng chưa tạo | Owner, purpose, approval và baseline |
| **ACTIVE** | Được phép dùng theo policy | Effective access, operations và audit |
| **ROTATING** | Đang chuyển sang version mới | Dependency coverage, rollback và progress |
| **DISABLED** | Tạm không cho sử dụng | Lý do, tác động và quyền bật lại |
| **REVOKED** | Không còn được tin cậy/cho phép theo mục đích | Verifier/consumer và dependent systems đã cập nhật? |
| **DECRYPT_ONLY / ARCHIVED** | Chỉ còn cần đọc dữ liệu cũ trong scope | Giới hạn principal/operation và ngày kết thúc |
| **COMPROMISED** | Có bằng chứng hoặc nghi vấn key bị lộ | Incident owner, containment và replacement |
| **PENDING_DESTRUCTION** | Đang chờ hủy theo quy trình | Dependency scan, approval, retention và recovery |
| **DESTROYED** | Material đã được hủy theo bằng chứng | Destruction record và xác minh bản sao |

Không tự chuyển DISABLED thành DESTROYED. Một key đã disable có thể vẫn tồn tại và có thể khôi phục; destruction phải có **bằng chứng và hậu quả được đánh giá**.

## 9. Kiểm thử key management

### 9.1. Ba lớp assurance

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| **Design effectiveness** | Lifecycle, quyền, cryptoperiod, backup, rotation và incident process có xử lý đúng risk scenarios? | Policy, threat model, key hierarchy, RACI, recovery design |
| **Implementation** | KMS/HSM, IAM, application và backup có cấu hình như thiết kế? | Key inventory, policy snapshot, IaC/config, deployment/change records |
| **Operating effectiveness** | Khóa có được dùng/rotation/thu hồi/khôi phục đúng trong kỳ? | Operation logs, rotation runs, access reviews, recovery drills, findings/retests |

### 9.2. Ma trận test

| Test | Expected behavior | Evidence |
|---|---|---|
| Principal ngoài quyền yêu cầu decrypt | Bị từ chối | Negative KMS/API test, audit event |
| App chỉ có encrypt nhưng thử decrypt | Bị từ chối nếu policy tách quyền | Effective policy và operation test |
| Workload ở dev dùng key prod | Bị chặn | Cross-environment negative test |
| Export raw key không được phép | Không thể export | HSM/KMS config và test theo phương pháp được phép |
| KMS policy thay đổi không phê duyệt | Bị chặn hoặc phát hiện/escalate | Change workflow, audit log, alert test |
| Rotation KEK | DEKs phụ thuộc được rewrap hoặc có disposition rõ | Dependency inventory, rewrap report, decrypt tests |
| Rotation DEK | Dữ liệu trong scope được migrate/đọc đúng theo version | Data migration results, version coverage, integrity tests |
| Key cũ bị disable | Workload không còn phụ thuộc ngoài exception | Usage logs, dependency scan, negative test |
| Recovery key | Có thể phục hồi theo quorum và không lộ material | Recovery drill, participants, evidence |
| Destroy key | Không còn dependency hợp lệ; destruction được duyệt | Approval, dependency scan, provider destruction record |
| Signing key rotation | Consumer xác minh đúng version mới và xử lý key cũ | Signature verification tests, trust metadata |
| Audit pipeline mất log | Coverage degraded và owner được báo | Synthetic failure, monitoring/alert evidence |

Không chạy test destructive trên production key nếu chưa có quy trình được phê duyệt và phương án phục hồi. Có thể dùng **test key, sandbox, non-production data và controlled simulation**; kết luận phải nêu giới hạn so với production.

### 9.3. Gherkin minh họa

~~~gherkin
Feature: Key management assurance

  Scenario: An unauthorized workload cannot decrypt payment data
    Given key K1 is restricted to the approved payment workloads
    And workload W1 is outside the approved principal scope
    When W1 requests a decrypt operation using K1
    Then the operation must be denied
    And the denial must be recorded in the key audit trail

  Scenario: A KEK rotation preserves approved data access
    Given DEKs are wrapped by KEK version 6
    And KEK version 7 is approved and active
    When the controlled rewrap process completes
    Then each in-scope DEK must have a verified wrapping disposition
    And authorized workloads must decrypt approved test data
    And no untracked dependency on version 6 may be reported as complete

  Scenario: A disabled key is not used by a legacy workload
    Given key K2 has been disabled after a controlled migration
    When a legacy workload attempts a cryptographic operation with K2
    Then the operation must be denied
    And the dependency must be investigated or documented as an approved exception

  Scenario: Key recovery requires the approved custodians
    Given the recovery policy requires an authorized quorum
    When fewer than the required independent custodians participate
    Then the recovery operation must not complete
    And the failed attempt must be auditable

  Scenario: A key cannot be destroyed while required data depends on it
    Given dataset D1 still requires key K3 for approved recovery
    When a destruction request for K3 is submitted
    Then the request must be blocked or escalated for an authorized decision
    And the dependency and decision must be recorded

  Scenario: Key operation telemetry failure is visible
    Given key operations must be sent to the security audit platform
    When the audit pipeline stops receiving expected events
    Then monitoring must report degraded assurance coverage
    And the designated control owner must be notified
~~~

### 9.4. Test phải kiểm tra cả hiệu ứng nghiệp vụ

Một KMS API trả AccessDenied là kết quả hữu ích, nhưng assurance cần xác minh:

- Không có **plaintext, wrapped DEK hoặc trạng thái nghiệp vụ** bị ghi ra ngoài.
- Không có retry hoặc fallback sang key khác trái policy.
- Không có workload/credential khác thực hiện cùng operation.
- Log có đủ **principal, key ID/version, operation, context, time, outcome** nhưng không chứa secret.
- Alert/ticket đến đúng owner khi có hành vi bất thường.

Với rotation, test giải mã được một sample sau rewrap chưa đủ nếu **population DEK** có hàng triệu bản ghi. Cần reconciliation theo inventory và thống kê **tổng số, thành công, lỗi, chưa xử lý, exception**.

## 10. Audit evidence và kết luận có giới hạn

### 10.1. Chuỗi truy vết

~~~mermaid
flowchart TD
    O["Data protection objective"] --> R["Risk: key disclosure,<br/>loss or misuse"]
    R --> Q["Key requirement /<br/>cryptoperiod / scope"]
    Q --> P["Key policy, hierarchy,<br/>owner and access controls"]
    P --> X["KMS/HSM operations,<br/>rotation, backup, recovery"]
    X --> T["Negative tests, rotation test,<br/>restore and audit review"]
    T --> E["Config, key inventory,<br/>operation logs, test results"]
    E --> D{"Evidence covers<br/>the actual dependencies?"}
    D -- "No" --> F["Finding, risk decision,<br/>remediation and retest"]
    F --> P
    D -- "Yes" --> A["Assurance claim<br/>with scope and limits"]
    A --> M["Monitoring, crypto agility<br/>and lifecycle review"]
    M --> R
~~~

### 10.2. Evidence package cho một key

Một hồ sơ kiểm chứng nên chứa:

1. **Key ID/version, purpose, algorithm reference, owner và trạng thái**.
2. System/environment/account/region và **dependency inventory**: dataset, DEK, app, backup, certificate/artifact.
3. KMS/HSM effective policy, allowed operations, principals, context và change history.
4. Key generation/import metadata, key ceremony/approval reference khi có.
5. Cryptoperiod, rotation plan, trigger và trạng thái migration.
6. Audit events cho generate/use/unwrap/sign/disable/rotation/export/admin changes.
7. Backup/recovery procedure, custodians, restore drill và kết quả.
8. Negative/positive test, expected/actual, version và environment.
9. Exception, compromise incident, finding, action owner và retest.
10. Destruction/retirement record và dependency reconciliation khi kết thúc.

**Không đưa key bytes, private key, DEK, KEK, seed hoặc recovery shares vào evidence package.** Lưu metadata và tham chiếu có kiểm soát tới bằng chứng được bảo vệ.

### 10.3. Claim–Argument–Evidence–Limitations

Ví dụ:

> **Claim:** KEK KEY-PAYMENTS-KEK-PROD được sử dụng để wrap DEKs của các dataset thanh toán trong phạm vi production đã kiểm tra; quyền unwrap giới hạn ở những workload được liệt kê trong policy hiện hành.
>
> **Argument:** Key nằm trong KMS boundary; policy gắn principal/operation; inventory liên kết DEKs và dataset; audit events ghi nhận operation; kiểm thử âm xác minh principal ngoài scope bị từ chối.
>
> **Evidence:** Key inventory version, effective policy snapshot, IAM principal list, KMS operation logs, negative tests, deployment IDs và access review.
>
> **Limitations:** Một nhóm export legacy và bản backup ở account vendor chưa có dependency/recovery evidence đầy đủ; không mở rộng kết luận sang các bản sao này cho đến khi có xác minh.

Kết luận cần nói rõ **key version, dữ liệu, môi trường, kỳ đánh giá và dependency coverage**. “Dùng KMS” hoặc “key không exportable” chỉ là một phần thiết kế/triển khai, không tự chứng minh quyền decrypt đã giới hạn hoặc backup có thể phục hồi.

## 11. Rotation và migration có thể kiểm chứng

### 11.1. Quy trình rotation an toàn

1. **Khởi tạo change:** Key ID, lý do, loại rotation, phạm vi, owner, cryptoperiod và risk.
2. **Lập dependency inventory:** Dataset/DEK, application, backup, replicas, vendor, certificate và consumer.
3. **Tạo version mới:** Theo baseline, kiểm tra key metadata, state và policy.
4. **Triển khai consumer:** Update key reference/config theo change plan; không chuyển alias tùy tiện.
5. **Migrate/rewrap/re-encrypt:** Thực hiện theo đúng loại khóa, idempotent và có trạng thái từng dependency.
6. **Verify:** Kiểm tra encrypt/decrypt/sign/verify đúng theo version; kiểm tra integrity và access scope.
7. **Reconcile:** Đối chiếu population và tất cả trạng thái dependency; theo dõi lỗi và ngoại lệ.
8. **Retire old version:** Chuyển sang decrypt-only/disabled/revoked theo policy khi đủ điều kiện.
9. **Destroy khi được phép:** Xác minh không còn dependency cần giữ, approval và recovery/retention đã giải quyết.
10. **Close evidence:** Change record, test, log, findings, người kiểm tra và residual risk.

### 11.2. Failure modes cần thiết kế trước

| Failure | Hậu quả | Control cần có |
|---|---|---|
| Version mới tạo nhưng app chưa dùng | Dữ liệu mới vẫn mã hóa bằng key cũ | Runtime key usage monitoring và rollout evidence |
| Một worker cũ chưa cập nhật | Rotation không đầy đủ | Dependency inventory, version usage scan |
| Rewrap thất bại giữa chừng | Một số DEK dùng KEK cũ | Idempotent workflow, checkpoint, reconciliation |
| Alias đổi nhưng metadata ciphertext không đổi | Consumer không biết key version | Explicit key ID/version metadata |
| Key cũ disable quá sớm | Không đọc được backup hoặc dữ liệu còn phụ thuộc | Pre-retirement dependency test |
| Rollback dùng lại key compromise | Rủi ro quay lại | Incident-aware rollback policy, không rollback mù |
| Audit pipeline mất event | Không biết migration đã làm gì | Local job evidence + telemetry health |
| Restore từ snapshot cũ | Wrapped DEK cũ quay lại | Restore compatibility và lifecycle reconciliation |

### 11.3. Pseudocode reconciliation

~~~text
rotation = createRotationRun(oldKeyVersion, newKeyVersion, approvedScope)
dependencies = loadVerifiedKeyDependencies(rotation.scope)

for dependency in dependencies:
    result = migrateAccordingToKeyType(dependency, rotation)
    recordExpectedAndActual(dependency, result)

    if result.failed or result.unverified:
        markDependencyOutstanding(dependency)
        notifyControlOwner(rotation, dependency)

coverage = reconcileAllDependencies(dependencies, rotation.results)

if coverage.hasUnknown or coverage.hasOutstanding:
    keepOldKeyInApprovedSafeState()
    doNotMarkRotationComplete()
    escalateGapsAndRisk()
else:
    runCryptographicAndBusinessIntegrityTests()
    obtainIndependentCompletionReview()
    retireOldKeyAccordingToApprovedPolicy()
~~~

Đây là logic minh họa. Không hủy key cũ chỉ dựa trên số lượng job thành công; phải xác định **mẫu số dependency đáng tin và những bản sao ngoài luồng**.

## 12. Backup và disaster recovery cho khóa

### 12.1. Vì sao backup key là bài toán riêng?

Mất database có thể phục hồi từ backup nếu key còn. Nhưng nếu mất **KEK duy nhất** bảo vệ toàn bộ DEK, backup dữ liệu vẫn có thể không sử dụng được. Ngược lại, backup key material không được bảo vệ có thể trở thành **đường compromise lớn hơn key chính**.

### 12.2. Các nguyên tắc cần đánh giá

- Backup/recovery có policy được duyệt, **scope, owner, custodians và retention** rõ.
- Backup key được bảo vệ bằng cơ chế phù hợp; quyền truy cập **tách khỏi operator dữ liệu**.
- M-of-N/quorum hoặc dual control áp dụng khi threat model yêu cầu.
- Có bản sao vùng/account/physical boundary khác theo mục tiêu phục hồi.
- Recovery không cho một người tự lấy toàn bộ key material ngoài quy trình.
- Restore test dùng **dữ liệu kiểm tra, key version và quy trình thực tế**; kiểm tra khả năng decrypt và integrity.
- Thay đổi key hierarchy hoặc provider phải cập nhật backup/recovery dependencies.
- Nếu recovery shares hoặc escrow tồn tại, phải quản lý vòng đời, thay custodians và hủy theo policy.

### 12.3. Recovery drill

Một cuộc thử nên xác minh:

1. Tình huống kích hoạt và người phê duyệt.
2. Custodians đủ điều kiện và độc lập tham gia.
3. Key/version được khôi phục đúng phạm vi, không lộ raw material.
4. Ứng dụng có thể unwrap DEK và giải mã dữ liệu test.
5. Dữ liệu khôi phục có **integrity và completeness** theo tiêu chí.
6. RPO/RTO đạt mục tiêu đã duyệt nếu áp dụng.
7. Audit logs, evidence, cleanup và trạng thái quyền sau drill.

Không chỉ ghi “đã phục hồi key thành công”. Cần chứng minh **workload hợp lệ thực sự sử dụng được khóa** và những quyền tạm thời đã được thu hồi sau bài thử.

## 13. Key compromise và incident response

### 13.1. Dấu hiệu cần điều tra

- Decrypt/sign requests bất thường theo principal, key hoặc khung thời gian.
- Thay đổi policy, exportability, key state hoặc rotation không có change ID.
- Nhiều lỗi authentication/authorization trên KMS/HSM.
- Key material xuất hiện trong repository, image, log, ticket hoặc máy trạm.
- Private key/certificate bị lộ, bất thường trong signature hoặc TLS deployment.
- Backup/escrow access ngoài quy trình hoặc custodians thay đổi bất thường.
- Key operation logs thiếu, ngắt quãng hoặc không đối chiếu được với workload.

Một alert không tự chứng minh compromise. Cần xác minh **actor, operation, resource, context, thời gian, hiệu ứng và nguồn telemetry**.

### 13.2. Quy trình ứng phó

| Giai đoạn | Hành động | Bằng chứng |
|---|---|---|
| **Triage** | Xác định key ID/version, loại khóa, dấu hiệu và độ tin cậy | Alert, KMS/HSM logs, incident ID |
| **Scope** | Xác định data, app, tenant, certificate, backup và consumer phụ thuộc | Dependency inventory, key usage history |
| **Containment** | Giới hạn/revoke/disable hoặc cô lập principal theo playbook | Decision/approval, state change, timestamps |
| **Replacement** | Tạo key mới, cập nhật consumer và trust | New key metadata, deployment/config, test |
| **Data remediation** | Re-encrypt/rewrap, đánh giá plaintext exposure, rotate credentials liên quan | Migration/reconciliation và integrity results |
| **Recovery** | Đảm bảo dữ liệu và dịch vụ cần thiết có thể hoạt động | Recovery test, RPO/RTO nếu áp dụng |
| **Investigation** | Bảo vệ logs, xác định nguyên nhân, bản sao và hành động đã xảy ra | Evidence chain, findings |
| **Closure** | Retest, cập nhật inventory/policy, residual risk và thông báo theo nghĩa vụ | Incident report, owner sign-off, follow-up |

Không phải mọi key compromise đều có cùng cách xử lý. **Signing key** có thể yêu cầu cập nhật trust và đánh giá chữ ký đã phát hành; **DEK** có thể yêu cầu đánh giá ciphertext và re-encryption; **KEK** có thể yêu cầu rewrap hàng loạt DEKs. Playbook phải phản ánh đúng mục đích khóa.

## 14. Cloud và third-party shared responsibility

### 14.1. Bản đồ trách nhiệm

| Thành phần | Provider có thể quản lý | Khách hàng/tổ chức vẫn cần kiểm chứng |
|---|---|---|
| KMS service availability | Hạ tầng dịch vụ theo cam kết | Dependency, failover, error handling và business recovery |
| HSM boundary | Phần cứng/firmware theo phạm vi provider | Key policy, principal, operation, import/export và admin separation |
| Default encryption | Cơ chế mã hóa nền tảng | Key choice, access, customer-managed keys và các bản export |
| Key rotation feature | Tạo version/rotation theo dịch vụ | Consumer migration, dependency coverage, old key retirement |
| Audit events | Phát sự kiện dịch vụ | Thu nhận, retention, alert routing và independent evidence |
| Backup/key recovery | Một số khả năng backup/replication | Recovery design, quyền, quorum, restore tests và nghĩa vụ |
| Managed database | Tích hợp KMS ở lớp dịch vụ | DB users, application plaintext, exports, snapshots và logs |

### 14.2. Câu hỏi với vendor

- Ai có quyền **administrative access** tới key management?
- Provider có thể truy cập hoặc khôi phục key material theo trường hợp nào?
- Key được bảo vệ trong **KMS/HSM boundary** nào và evidence/certification có scope gì?
- Rotation/disable/deletion hoạt động ra sao; khách hàng có chủ động kiểm soát?
- Có thể export, import hoặc di chuyển key sang provider khác không?
- Log nào được cung cấp; khách hàng có nhận đủ principal/operation/outcome?
- Khi chấm dứt dịch vụ, dữ liệu và key được trả/xóa thế nào?
- Nếu provider outage, key không truy cập được hoặc provider ngừng dịch vụ, kế hoạch khôi phục?

Chứng nhận của nhà cung cấp chỉ hỗ trợ kết luận trong **dịch vụ, phiên bản, thời kỳ và phạm vi được đánh giá**. Nó không chứng minh tenant policy, app authorization hoặc key dependencies của khách hàng đã đúng.

## 15. Đo hiệu quả key management

### 15.1. Các chỉ số cần theo dõi

| Metric | Ý nghĩa | Cảnh báo khi diễn giải |
|---|---|---|
| **Key inventory coverage** | Tỷ lệ key resources đã được ghi nhận trong scope | Nguồn KMS/account chưa quét không được tính là rỗng |
| **Owner coverage** | Key có owner/control owner phù hợp | Có tên owner chưa chứng minh họ có trách nhiệm thực tế |
| **Policy review coverage** | Key policy được rà soát đúng kỳ | Review không kiểm tra effective permissions có thể hời hợt |
| **Rotation compliance** | Key tới hạn đã xử lý theo policy | Alias đổi chưa chứng minh dependency migration |
| **Outstanding dependencies** | Dataset/workload còn dùng old key | Phải biết mẫu số và nguồn discovery |
| **Unauthorized operation attempts** | Tín hiệu quyền sai hoặc hành vi bất thường | Không có alert có thể do log thiếu |
| **Recovery test success** | Khả năng phục hồi key và dữ liệu | Một lần test không đại diện mọi version/region |
| **Key compromise response time** | Thời gian containment/replacement theo playbook | Cần tách phát hiện, quyết định và hoàn tất |
| **Keys past cryptoperiod** | Khóa quá hạn hoặc chưa được đánh giá | Ngoại lệ không được gộp vào compliant |
| **Destruction evidence coverage** | Hủy khóa có approval và dependency check | Disable không đồng nghĩa destroy |
| **Audit pipeline health** | Key events được thu nhận đầy đủ | Job lỗi phải đánh dấu degraded |

### 15.2. Ví dụ tính rotation coverage

Giả sử một KEK cũ có **500 DEK phụ thuộc** trong inventory đã xác minh. Rotation run đã rewrap 470 DEK thành công, 20 lỗi và 10 chưa xác minh:

~~~text
Verified rewrap coverage = 470 / 500 = 94%
Outstanding dependencies = 20 + 10 = 30
~~~

Không thể báo rotation hoàn tất 100% chỉ vì KMS đã tạo version mới. 30 dependency còn lại cần **owner, trạng thái, rủi ro, hành động và tiêu chí retest**. Nếu inventory thiếu một backup account, mẫu số 500 vẫn chưa chắc đầy đủ.

### 15.3. Không tối ưu số lượng khóa đơn thuần

Ít khóa có thể dễ vận hành nhưng tạo **blast radius lớn**; nhiều khóa có thể cô lập tốt nhưng làm tăng gánh nặng inventory, rotation, backup và audit. Chọn granularity dựa trên:

- Tenant isolation và phân vùng dữ liệu.
- Mức nhạy cảm, quy mô và mục đích.
- Khả năng giới hạn principal và operation.
- Khả năng rotate/rewrap/recover trong thời gian yêu cầu.
- Chi phí, quota, latency và operational resilience.
- Khả năng chứng minh coverage, không chỉ số lượng key objects.

## 16. Tình huống tổng hợp: KMS có key version mới nhưng dữ liệu vẫn phụ thuộc khóa cũ

Một nền tảng thanh toán lưu dữ liệu giao dịch trong database và object storage. Nhóm cloud bật **automatic KEK rotation** và dashboard cho thấy key đã chuyển từ version 4 sang version 5. Báo cáo assurance ghi “rotation hoàn tất”.

Kiểm tra sâu hơn phát hiện:

1. Ứng dụng mới dùng KEK version 5, nhưng một **batch worker legacy** vẫn giữ alias/version cũ.
2. Một phần DEK đã được wrap bằng version 4; chưa có **dependency reconciliation** để biết số lượng chính xác.
3. Backup DR ở account khác có wrapped DEKs cũ, nhưng team chưa thực hiện restore test sau rotation.
4. Một service identity có quyền **Decrypt** trên KEK cho cả môi trường staging và production.
5. Operator có thể sửa policy và xóa log ở cùng một account; không có review độc lập.
6. Một CSV export chứa plaintext trong bucket phụ, nên rotation KEK không ảnh hưởng bản sao đó.

### 16.1. Vì sao kết luận ban đầu không đúng?

| Nhận định | Thực tế |
|---|---|
| Version 5 active nghĩa mọi DEK đã chuyển | Version mới có thể chỉ áp dụng cho operation mới |
| Rotation KMS thành công nghĩa dữ liệu cũ đã rewrap | Cần biết cơ chế rotation và trạng thái từng dependency |
| Backup được mã hóa nên khôi phục được | Chưa kiểm tra key version, quyền và restore |
| Một service account dùng chung thuận tiện | Có thể tạo quyền decrypt quá rộng giữa môi trường |
| KMS giữ key nên log đã an toàn | Operator có thể xóa evidence nếu quyền không tách |
| Dữ liệu đều được mã hóa bởi KEK | CSV plaintext nằm ngoài key hierarchy |

### 16.2. Kế hoạch khắc phục

**Inventory:** Lập danh sách DEK, wrapped key version, dataset, batch worker, backup, export, tenant và principal. Đối chiếu với nguồn KMS và storage độc lập.

**Access control:** Tách service identities theo môi trường và purpose; thu hẹp quyền decrypt/unwrap; tách quản trị policy khỏi quyền sửa/xóa audit evidence.

**Migration:** Xác định rewrap hay re-encryption phù hợp cho từng dependency; thực hiện theo batch có checkpoint và retry an toàn.

**Backup/recovery:** Restore thử backup có wrapped DEK version cũ và xác minh dữ liệu; chỉ retire old KEK khi đủ căn cứ và có quyết định.

**Plaintext exports:** Đánh giá quyền bucket, retention, download path và cách loại bỏ/di chuyển bản sao theo policy; không cho rằng rotation đã bảo vệ chúng.

**Audit:** Kiểm tra KMS operation events, policy changes, pipeline health và alert routing; bảo vệ log độc lập.

**Assurance retest:** Kiểm thử workload ngoài scope, cross-environment, batch legacy, DEK rewrap coverage, restore và old-key disable; lưu expected/actual và residual gaps.

### 16.3. Kết luận assurance có giới hạn

> **Claim:** KMS đã tạo và kích hoạt KEK version 5 cho các operation được ghi nhận trong production tại thời điểm kiểm tra.
>
> **Evidence:** Key metadata, rotation configuration và KMS key-version event.
>
> **Limitations:** Chưa chứng minh mọi DEK đã rewrap, batch legacy đã chuyển, backup cũ có thể phục hồi, quyền decrypt được phân tách theo môi trường hoặc plaintext export được bảo vệ.
>
> **Follow-up:** Ghi findings cho dependency coverage, cross-environment access, backup recovery, audit SoD và export protection; chỉ kết luận rotation hoàn tất sau reconciliation và retest.

## 17. Những sai lầm thường gặp

| Sai lầm | Vì sao chưa đủ? | Cách cải thiện |
|---|---|---|
| Coi encryption enabled là key management đạt | Không chứng minh lifecycle, quyền và recovery | Kiểm tra vòng đời và evidence |
| Lưu raw key trong repo/config | Lịch sử commit và artifact có thể giữ bản sao | KMS/secret manager, rotate và revoke key đã lộ |
| Một key dùng cho nhiều mục đích | Tăng blast radius và rủi ro protocol misuse | Tách key theo purpose |
| Dùng chung key giữa dev/staging/prod | Môi trường yếu có thể ảnh hưởng production | Tách key/policy theo environment |
| Gộp encrypt/decrypt/admin vào một role | Quyền quá rộng, khó audit | Tách principal và operation |
| Cho rằng non-exportable đồng nghĩa không thể lạm dụng | App vẫn có thể gọi decrypt/sign | Authorization theo context và monitoring |
| Đổi alias rồi tuyên bố rotation xong | Dependency vẫn dùng old version | Version inventory, reconciliation và retest |
| Rewrap và re-encryption bị coi là một | Khác phạm vi dữ liệu và operation | Xác định đúng loại rotation |
| Xóa old key ngay sau rotation | Backup/replica có thể còn phụ thuộc | Dependency check, restore test và approval |
| Backup key nhưng không thử recovery | Có thể thiếu quorum hoặc không giải mã được | Recovery drill với dữ liệu kiểm tra |
| HSM/KMS được xem là tự giải quyết mọi vấn đề | Policy/app/operation/log vẫn có thể sai | Shared responsibility và control testing |
| KMS admin có thể xóa log | Mất bằng chứng độc lập | SoD, log integrity và external audit store |
| Key inventory lưu secret material | Inventory trở thành kho lộ khóa | Chỉ lưu metadata/reference có phân quyền |
| Disable bị hiểu là destroy | Key vẫn tồn tại hoặc có thể bật lại | Trạng thái và destruction evidence riêng |
| Không có key dependency map | Incident/rotation không biết phạm vi | Liên kết key–dataset–workload–backup |
| Không kiểm tra export plaintext | Rotation không bảo vệ bản sao ngoài encryption boundary | Data inventory, export controls và lifecycle |
| Báo cáo 100% theo nguồn KMS duy nhất | Bỏ sót keys ngoài scope, imported hoặc legacy | Reconcile nhiều nguồn và ghi unknown |

## 18. Bài tập thực hành

### Bài tập 1 — Thiết kế key hierarchy

Một hệ thống lưu **hồ sơ khách hàng, chỉ thị thanh toán và audit logs** trong database, object storage và backup. Có ba môi trường dev/staging/prod.

**Yêu cầu:** Thiết kế key hierarchy gồm DEK/KEK hoặc cấu trúc phù hợp, phân vùng theo purpose/environment/tenant, owner, principal và recovery dependency. Giải thích tại sao không nên dùng chung một khóa cho cả ba nhóm dữ liệu.

### Bài tập 2 — Phân tích quyền KMS

Một application identity có quyền encrypt/decrypt trên mọi key trong production account. Một operator có quyền sửa policy, tạo key và xóa audit log.

**Yêu cầu:** Nhận diện ít nhất **sáu rủi ro**, đề xuất policy theo principal/operation/resource/context, phân tách vai trò và test âm. Xác định bằng chứng cho thấy policy có hiệu lực thực tế.

### Bài tập 3 — Phân biệt rotation

Một KEK được tự động đổi version. 1.000 DEK vẫn đang lưu wrapped bởi version cũ; một số ciphertext nằm trong backup.

**Yêu cầu:** Viết kế hoạch **KEK rewrap**, tiêu chí coverage, xử lý lỗi, kiểm tra backup và điều kiện disable/destroy version cũ. Giải thích tại sao không thể báo hoàn tất chỉ từ event “new key version created”.

### Bài tập 4 — Xử lý key compromise

Private signing key của một service có dấu hiệu bị lộ trong CI artifact. Token và artifact đã được ký trong một khoảng thời gian chưa xác định.

**Yêu cầu:** Lập incident plan từ triage/scope tới revoke, phát hành key mới, cập nhật verifier/trust, đánh giá chữ ký cũ, audit và thông báo. Nêu những bằng chứng cần bảo toàn và cách kiểm tra consumer đã ngừng tin khóa cũ.

### Bài tập 5 — Kiểm tra backup/recovery

Một tổ chức có KMS-managed key, backup ở account khác và quy trình khôi phục cần ba custodians. Lần diễn tập trước chỉ có một operator chạy được lệnh restore.

**Yêu cầu:** Xác định design/implementation/operating gaps, thiết kế recovery drill đúng quorum, test dữ liệu giải mã và thu hồi quyền tạm. Viết acceptance criteria cho kết luận “có thể phục hồi”.

### Bài tập 6 — Audit evidence

Nhóm bảo mật cung cấp screenshot “key is enabled”, dashboard encryption và một file CSV liệt kê key aliases. Không có principal list, key dependency map, rotation test hoặc operation logs.

**Yêu cầu:** Viết **Claim–Argument–Evidence–Limitations**, xác định điều có thể kết luận và liệt kê ít nhất sáu bằng chứng/test bổ sung trước khi khẳng định key management hiệu quả.

### Bài tập 7 — Crypto agility

Một hệ thống dùng algorithm baseline cũ; dữ liệu phải lưu dài hạn và có nhiều bản sao ở analytics/vendor. Một thay đổi baseline yêu cầu chuyển sang thuật toán được tổ chức phê duyệt.

**Yêu cầu:** Lập inventory dependency, migration plan, dual-read/new-write strategy nếu phù hợp, backup/restore, consumer compatibility, test integrity và tiêu chí ngừng thuật toán cũ. Nêu cách quản lý dữ liệu cũ chưa thể chuyển.

### Bài tập 8 — Kiểm tra key destruction

Một KEK sắp đến ngày hủy. KMS không còn ghi nhận operation trong 90 ngày, nhưng chưa có đối chiếu backup cũ và vendor archive.

**Yêu cầu:** Giải thích tại sao “không có operation gần đây” không chứng minh không còn dependency. Xây dependency reconciliation, retention/legal review, independent approval, restore test và destruction evidence.

## 19. Checklist đánh giá Key management

- **Purpose:** Mỗi key có mục đích, scope, owner và thuật toán/baseline được duyệt không?
- **Generation:** Khóa được tạo bằng nguồn/CSPRNG phù hợp; có metadata và không lộ material không?
- **Hierarchy:** DEK, KEK, root/signing/TLS keys có vai trò và quan hệ rõ không?
- **Inventory:** Có key ID/version, dependencies, workload, data copies, environment và trạng thái không?
- **Storage:** Key nằm trong boundary phù hợp; raw material không ở repo, image, log hoặc ticket không?
- **Access:** Principal/operation/resource/context có least privilege; encrypt/decrypt/admin có được tách không?
- **SoD:** Người tạo/cấp quyền/sử dụng/duyệt/hủy/log review có phân tách phù hợp không?
- **Usage:** KMS requests có authorization, context, audit và chống decryption oracle không?
- **Rotation:** Cryptoperiod và trigger có được phê duyệt; migration/reconciliation chứng minh mọi dependency chưa?
- **Revocation:** Khi compromise, có playbook scope/containment/replacement/retest không?
- **Backup:** Key recovery có bảo vệ, quorum/custodian và restore drill thực tế không?
- **Destruction:** Có dependency check, retention/hold review, approval và destruction evidence không?
- **Crypto agility:** Có algorithm/key version inventory, migration và ngừng hỗ trợ an toàn không?
- **Third party:** Provider/vendor responsibility, key custody, logs, recovery và contract scope có được xác minh không?
- **Testing:** Có negative tests, rotation, backup/recovery, access review, telemetry health và failure paths không?
- **Evidence:** Có policy version, key metadata, effective permissions, operation logs, expected/actual và limitations không?
- **Continuous assurance:** Thay workload, data flow, KMS policy, vendor hoặc incident có trigger review và retest không?

**Điều cần ghi nhớ:** Key management không dừng ở việc tạo khóa trong KMS hay bật mã hóa cho database. Nó là **quản lý có kiểm soát toàn bộ vòng đời và mọi phụ thuộc của khóa**: ai tạo, ai dùng, dùng cho dữ liệu nào, ai được thay đổi, rotation đã chuyển hết chưa, backup có phục hồi được không và khi nào có thể hủy. Trong **security assurance**, chỉ nên kết luận khóa được quản lý hiệu quả khi **inventory đủ tin cậy, quyền thực tế được kiểm thử, vòng đời có bằng chứng, recovery được diễn tập và các ngoại lệ/điểm yếu được theo dõi tới khi xử lý**.
