# Quản lý bí mật, chứng chỉ, khóa mã hóa và luân chuyển

Ứng dụng cloud cần nhiều thông tin nhạy cảm để kết nối và bảo vệ dữ liệu: mật khẩu database, API token, private key, chứng chỉ TLS, khóa mã hóa và credential của workload. Nếu các giá trị này được lưu trong source code, image, file cấu hình hoặc log, một lần lộ repository hay quyền truy cập quá rộng có thể mở đường vào nhiều hệ thống. Ngay cả khi bí mật được lưu an toàn, credential không có thời hạn, không có owner và không có quy trình thu hồi vẫn tạo rủi ro dài hạn.

**Quản lý bí mật (secrets management)**, **quản lý chứng chỉ (certificate management)** và **quản lý khóa mã hóa (key management)** là ba năng lực liên quan nhưng có mục đích khác nhau. Secret xác thực danh tính hoặc cấp quyền truy cập; certificate chứng minh danh tính và hỗ trợ thiết lập kênh tin cậy; encryption key bảo vệ tính bí mật hoặc tính toàn vẹn của dữ liệu. Luân chuyển (rotation) thay thế tài sản cũ bằng phiên bản mới có kiểm soát, trong khi hệ thống vẫn hoạt động và vẫn có thể đọc dữ liệu đã mã hóa trước đó.

Bài học thuộc chương **Kiến trúc bảo mật** của lộ trình **Cloud Architecture**. Chương trình hướng dẫn thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ tới mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Nội dung tập trung vào việc giảm quyền truy cập, quản lý vòng đời credential, bảo vệ khóa và thiết kế rotation có thể kiểm chứng.

Sau bài học, bạn có thể:

- Phân biệt secret, credential, certificate, public/private key và encryption key.
- Thiết kế central secret store, workload identity và access policy theo least privilege.
- Sử dụng KMS/HSM và envelope encryption đúng mục đích.
- Quản lý TLS certificate, trust chain, expiry, renewal và revocation.
- Thiết kế key hierarchy, key version, rotation và crypto-erasure.
- Luân chuyển credential mà không tạo downtime hoặc làm hỏng kết nối.
- Phát hiện rò rỉ, thu hồi, điều tra và phục hồi sau compromise.
- Thiết lập audit, inventory, alert và SLO cho tài sản mật mã.

## 1. Phân biệt secret, certificate và encryption key

Các tài sản này có thể cùng tồn tại trong một kết nối nhưng giải quyết các vấn đề khác nhau.

| Tài sản | Mục đích | Ví dụ | Rủi ro nếu lộ/hết hạn |
| --- | --- | --- | --- |
| Secret | Giữ thông tin bí mật dùng để xác thực hoặc truy cập | DB password, API token, webhook signing secret | Kẻ khác có thể giả danh hoặc gọi API |
| Credential | Dữ liệu/đối tượng đại diện quyền truy cập | Username/password, OAuth client credential | Quyền bị lạm dụng |
| Certificate | Gắn danh tính với public key qua CA signature | TLS server certificate, client certificate | Mất khả năng xác thực hoặc bị giả mạo nếu private key lộ |
| Public key | Dùng để verify signature hoặc mã hóa theo thuật toán phù hợp | Public key trong certificate | Thường không cần giữ bí mật nhưng cần xác minh nguồn và fingerprint |
| Private key | Thực hiện ký, giải mã hoặc xác thực tùy thuật toán | TLS private key, signing key | Lộ key có thể cho phép giả danh hoặc giải mã |
| Data encryption key (DEK) | Mã hóa dữ liệu thực tế | AES key cho object/database field | Dữ liệu tương ứng có thể bị giải mã |
| Key encryption key (KEK) | Mã hóa/bọc DEK | KMS-managed key | Có thể mở quyền giải mã nhiều DEK |
| Root/CA key | Ký chứng chỉ cấp dưới hoặc tạo trust chain | Private key của intermediate/root CA | Compromise có thể ảnh hưởng rộng toàn hệ thống |

Một certificate thường không bí mật; nó chứa public key và thông tin danh tính. Private key đi kèm mới là tài sản phải bảo vệ. Encryption key cũng không giống password: key thường được dùng bởi thuật toán mật mã và cần quản lý version, usage, algorithm, lifecycle và quyền decrypt/unwrap chính xác.

## 2. Xác định threat model và phân loại tài sản

Không thể bảo vệ mọi secret với cùng một mức kiểm soát. Cần lập inventory và đánh giá impact nếu tài sản bị lộ, mất, sửa đổi hoặc không thể truy cập.

Một inventory tối thiểu nên gồm:

- Asset ID và loại tài sản.
- Owner/đội chịu trách nhiệm và service sử dụng.
- Mục đích, environment, tenant và resource scope.
- Secret reference hoặc key ID; không đưa plaintext vào inventory.
- Quyền đọc, ghi, rotate, revoke, decrypt và administer.
- Ngày tạo, version hiện tại, ngày hết hạn và lịch rotation.
- Phụ thuộc, ứng dụng/client đang dùng và quy trình rollback.
- Phân loại dữ liệu, mức impact và yêu cầu compliance.
- Trạng thái: active, staged, deprecated, revoked hoặc destroyed.

Ví dụ DB credential production có thể được phân loại critical vì nó mở quyền ghi dữ liệu giao dịch. API token chỉ đọc metadata có thể có impact thấp hơn, nhưng nếu dùng chung cho mọi tenant thì blast radius vẫn lớn.

### 2.1. Phân cấp bảo vệ

| Mức | Ví dụ | Kiểm soát thường cần |
| --- | --- | --- |
| Critical | Root/CA private key, payment signing key, database admin credential | HSM hoặc KMS phù hợp, quyền rất hẹp, dual control, audit và quy trình khẩn cấp |
| High | Production service credential, DEK/KEK, TLS private key | Secret manager/KMS, workload identity, rotation và monitoring |
| Moderate | Credential giới hạn cho staging hoặc service đọc | Central store, scoped access, expiry và audit |
| Public | Public certificate, public verification key | Integrity/provenance, version và distribution đúng |

Phân loại phải theo khả năng khai thác và phạm vi quyền thực tế, không chỉ dựa trên tên tài sản.

## 3. Centralized secret management

Secret manager/vault cung cấp nơi lưu bí mật tập trung, kiểm soát truy cập, version, audit và tích hợp rotation. Nó giảm nhu cầu nhúng secret trong repository, image hoặc file cấu hình.

Một secret management service thường hỗ trợ:

- Mã hóa secret at rest và in transit.
- Access policy theo workload identity, resource, environment hoặc tenant.
- Versioning và metadata.
- Audit log cho read/write/rotate/delete.
- Automatic rotation hoặc tích hợp rotation workflow.
- Secret injection hoặc API retrieval.
- Expiry, revoke và alert.
- Replication/backup theo khả năng dịch vụ.

Centralization không có nghĩa một administrator hoặc một root credential được đọc mọi secret. Quyền quản trị secret store cần được phân tách theo environment, tenant, business domain và loại operation.

### 3.1. Không lưu secret trong source code hoặc artifact

Các vị trí không nên chứa plaintext secret:

- Git repository, kể cả private repository.
- Docker image, VM image hoặc package.
- Frontend bundle, mobile app hoặc JavaScript gửi tới browser.
- Terraform/CloudFormation plan/state nếu không có bảo vệ và lifecycle phù hợp.
- CI/CD log, build output và crash dump.
- Application log, tracing attribute hoặc metric label.
- Ticket, chat, wiki hoặc tài liệu vận hành chia sẻ rộng.
- Test fixture hoặc database dump dùng ngoài production.

Environment variable có thể là phương tiện inject secret cho một số runtime, nhưng không tự làm secret an toàn. Nó có thể bị lộ qua process inspection, crash dump, debug endpoint hoặc log nếu không kiểm soát. Ưu tiên cơ chế identity-based retrieval hoặc secret mount/runtime integration phù hợp nền tảng.

### 3.2. Secret reference thay vì giá trị

Application config chỉ nên chứa reference, ví dụ secret path/ARN/resource ID và version policy. Khi runtime cần kết nối, nó xác thực bằng workload identity và lấy secret trong phạm vi cho phép.

~~~yaml
database:
  host: db.internal.example
  credentialRef: secret://production/booking/database
  credentialVersionPolicy: current
tls:
  certificateRef: cert://production/booking-api
~~~

Đây là ví dụ khái niệm, không phải URI chuẩn của nhà cung cấp. Secret manager và certificate manager có syntax riêng. Không đưa plaintext password, token hoặc private key trực tiếp vào YAML.

## 4. Workload identity và least privilege

Một ứng dụng không nên dùng chung một credential tĩnh có quyền rộng chỉ để lấy các secret khác. Hãy xác thực workload bằng identity do platform cấp: IAM role/service account, managed identity, SPIFFE/SPIRE identity hoặc cơ chế tương đương.

Luồng khái niệm:

~~~mermaid
sequenceDiagram
    participant W as Application workload
    participant I as Identity provider
    participant S as Secret manager
    participant D as Database

    W->>I: Request workload identity/token
    I-->>W: Short-lived identity token
    W->>S: Read authorized secret reference
    S-->>W: Secret value/version
    W->>D: Authenticate using scoped credential
~~~

Workload identity giúp loại bỏ bootstrap password dài hạn trong cấu hình. Tuy nhiên, trust policy phải kiểm tra service, namespace, environment, audience và subject cụ thể. Không cấp quyền đọc toàn bộ secret chỉ vì workload thuộc một cloud account/project.

### 4.1. Tách quyền theo operation

Quyền đọc secret, tạo version mới, rotate, revoke và xóa là các quyền khác nhau.

- Runtime thường chỉ cần read một số secret cụ thể.
- Rotation worker cần quyền tạo version mới và cập nhật credential phía đích.
- Operator có thể cần xem metadata nhưng không cần đọc plaintext.
- Security administrator quản lý policy và audit, nhưng không nhất thiết được dùng credential nghiệp vụ.
- Destroy key hoặc xóa version cần approval/quy trình đặc biệt.

### 4.2. Tenant-aware secret access

Với SaaS đa tenant, secret reference và policy phải gắn tenant. Runtime đang xử lý tenant A không được đọc credential ERP của tenant B dù hai tenant cùng dùng một worker pool.

Nếu secret path có tenant ID, điều đó chỉ hỗ trợ định tuyến; backend vẫn phải xác minh identity và policy. Không tin tenant ID do client truyền để quyết định secret access.

## 5. Secret rotation và vòng đời credential

Rotation thay credential đang dùng bằng credential mới, đồng thời cập nhật bên phát hành và các consumer. Mục tiêu là giới hạn thời gian một credential bị lộ có thể bị khai thác và giảm rủi ro credential tồn tại lâu.

Vòng đời thường gồm:

1. **Provision:** tạo credential tại hệ thống sở hữu.
2. **Store:** lưu phiên bản mới trong secret manager.
3. **Distribute:** cấp quyền cho workload nhận version mới.
4. **Switch:** ứng dụng bắt đầu dùng credential mới.
5. **Verify:** xác nhận kết nối và thao tác nghiệp vụ hoạt động.
6. **Revoke old:** thu hồi credential cũ sau khi consumer đã chuyển.
7. **Audit/cleanup:** ghi nhận version, thời điểm, owner và kết quả.

Không cập nhật secret store rồi lập tức thu hồi credential cũ nếu ứng dụng vẫn giữ connection pool hoặc worker cũ. Cần một giai đoạn overlap có thời hạn và được giám sát.

### 5.1. Hai-phase rotation cho credential có thể overlap

~~~mermaid
flowchart TD
    A["Create credential B"] --> B["Store version B"]
    B --> C["Allow A and B temporarily"]
    C --> D["Refresh application clients"]
    D --> E{"All clients verified on B?"}
    E -- "No" --> F["Investigate / retry / rollback window"]
    F --> D
    E -- "Yes" --> G["Revoke credential A"]
    G --> H["Close overlap and audit"]
~~~

Không phải hệ thống nào cũng cho phép hai credential đồng thời. Với password database đơn, có thể cần hai database users hoặc cơ chế staged credential để tránh downtime. Thiết kế rotation phải theo khả năng của target system.

### 5.2. Rotation cadence và event-driven rotation

Không có một chu kỳ rotation phù hợp cho mọi secret. Chính sách nên xét:

- Impact nếu credential bị lộ.
- Credential có thời hạn hay không.
- Hỗ trợ tự động rotate của provider.
- Số lượng consumer và thời gian cập nhật.
- Khả năng revoke ngay.
- Compliance và policy của tổ chức.
- Chi phí và rủi ro tạo lỗi do rotate quá thường xuyên.

Ngoài lịch định kỳ, phải rotate ngay khi nghi ngờ compromise, nhân sự/nhà cung cấp thay đổi quyền, scope mở rộng hoặc credential bị lưu nhầm trong log/repository.

## 6. Dynamic secrets và short-lived credentials

Dynamic secrets được tạo theo yêu cầu, có TTL và thường tự hết hiệu lực hoặc được revoke khi lease kết thúc. Ví dụ secret manager cấp database user tạm thời cho một service hoặc token truy cập cloud có thời hạn ngắn.

Ưu điểm:

- Giảm thời gian credential có thể bị khai thác.
- Hạn chế secret tồn tại lâu trong config.
- Mỗi workload/lease có thể được audit riêng.
- Giảm nhu cầu rotation tĩnh quy mô lớn.

Đánh đổi:

- Runtime phải xử lý expiry, renew và revoke.
- Database/target phải hỗ trợ tạo credential động.
- Nếu secret manager không khả dụng, cấp mới có thể thất bại.
- Connection pool cần refresh trước khi credential hết hạn.
- Số lượng user/role tạm có thể tạo áp lực lên database.

### 6.1. TTL phải dài hơn nhu cầu nhưng ngắn theo risk

Credential TTL quá ngắn có thể làm tăng request tới secret manager và tạo gián đoạn khi dependency chậm. TTL quá dài lại giảm lợi ích của ephemeral credential. Cần có renew window, jitter, cache an toàn và behavior khi renew thất bại.

Không ghi token ngắn hạn vào log chỉ vì nó sắp hết hạn; trong khoảng còn hiệu lực, token vẫn có giá trị khai thác.

## 7. Quản lý TLS certificate

TLS certificate chứng minh danh tính server/client và gắn public key với danh tính qua CA signature. Hệ thống thường dùng server certificate để client xác minh endpoint; mTLS yêu cầu cả hai phía xác thực certificate của nhau.

Các thành phần:

- **Subject/SAN:** tên DNS hoặc danh tính certificate đại diện.
- **Public key:** khóa công khai trong certificate.
- **Private key:** khóa bí mật tương ứng, được dùng trong TLS handshake theo thuật toán.
- **Issuer/CA:** tổ chức hoặc authority ký certificate.
- **Validity period:** thời gian certificate có hiệu lực.
- **Certificate chain:** chuỗi certificate từ leaf tới intermediate/root trust anchor.
- **Key usage/EKU:** giới hạn mục đích sử dụng.
- **Revocation mechanism:** trạng thái thu hồi qua CRL/OCSP hoặc policy tương ứng.

### 7.1. Certificate lifecycle

Một vòng đời điển hình:

1. Tạo private key trong môi trường bảo vệ phù hợp.
2. Tạo CSR với SAN và usage đúng.
3. Gửi CSR tới CA được tin cậy.
4. Nhận certificate và chain.
5. Validate name, chain, expiry, usage và key pair.
6. Deploy certificate/key tới endpoint.
7. Verify TLS handshake từ các client đại diện.
8. Theo dõi expiry và renew trước deadline.
9. Revoke khi private key compromise hoặc certificate không còn được tin cậy.
10. Xóa/disable private key theo retention và forensic policy.

Không tái sử dụng cùng private key cho mọi service hoặc mọi tenant nếu không cần thiết. Key reuse tạo phạm vi tác động rộng hơn khi một endpoint bị compromise.

### 7.2. SAN và hostname validation

Certificate cần chứa đúng DNS name/IP mà client dùng để kết nối trong Subject Alternative Name (SAN). Một certificate được ký bởi CA đáng tin nhưng thiếu hostname phù hợp vẫn phải bị client từ chối. Không tắt hostname verification để “sửa” lỗi certificate mismatch trong production.

### 7.3. Chain và trust store

Một certificate leaf có thể hợp lệ nhưng client không tin CA intermediate/root hoặc server không gửi đủ chain. Cần kiểm tra trust store trên tất cả client/runtime, đặc biệt khi chuyển CA, rotate intermediate hoặc nâng image/base OS.

## 8. Certificate renewal và rotation không downtime

Certificate hết hạn có thể khiến client không kết nối được, dù application và network vẫn đang khỏe. Cần alert theo ngày còn lại, tự động renew và deploy theo thứ tự.

Một quy trình có overlap:

- Phát hành certificate mới và private key tương ứng.
- Kiểm tra SAN, chain, usage và key pair.
- Cài certificate mới lên một số instance/cell.
- Thực hiện TLS handshake từ client thực tế.
- Mở rộng deploy theo cohort.
- Đảm bảo load balancer/proxy và backend đều có certificate phù hợp.
- Giữ đường quay lui trong thời gian được kiểm soát.
- Thu hồi certificate/key cũ nếu cần và audit hoàn tất.

Với client pin certificate hoặc pin public key, rotation còn cần cập nhật pinset theo chiến lược overlap. Không được chỉ thay server certificate rồi giả định mọi client sẽ chấp nhận.

### 8.1. Expiry monitoring

Theo dõi tối thiểu:

- Certificate expiry date và days-to-expiry.
- SAN/hostname mismatch.
- Issuer/chain/trust status.
- Renewal job success/failure.
- Tỷ lệ TLS handshake failure.
- Certificate version trên từng endpoint/region/cell.
- Client pinning compatibility nếu có.

Alert chỉ khi còn 1 ngày có thể quá muộn nếu pipeline renew cần nhiều approval hoặc deployment window. Threshold phải dựa trên lead time phục hồi và lịch phát hành.

## 9. mTLS và service-to-service identity

Trong môi trường microservices hoặc zero-trust, mTLS có thể xác thực cả client lẫn server. Mỗi workload có identity certificate riêng và policy quyết định service nào được gọi service nào.

mTLS không tự thay authorization nghiệp vụ. Certificate chứng minh workload identity, nhưng policy vẫn cần xác định action/resource được phép. Một service được xác thực vẫn có thể không được phép đọc dữ liệu tenant hoặc gọi operation quản trị.

Cần quản lý:

- CA trust hierarchy và issuance policy.
- Workload identity/SAN mapping.
- Certificate TTL và automatic renewal.
- Rotation không gây đồng thời trust mismatch.
- Revocation và phản ứng khi key compromise.
- Sidecar/service mesh control plane availability.
- Audit identity và policy decision.

## 10. Khóa mã hóa và KMS

Key management service (KMS) cung cấp lifecycle và policy cho cryptographic keys: tạo, lưu, sử dụng, rotate, disable và audit. Một số workload cần hardware security module (HSM) để bảo vệ key material trong phần cứng đạt yêu cầu hoặc thực hiện thao tác nhạy cảm trong boundary được kiểm soát.

KMS/HSM không tự xác định dữ liệu nào cần mã hóa, ai được phép decrypt hoặc cách khôi phục khi key bị disable. Application và data architecture vẫn phải định nghĩa scope, key policy và recovery.

### 10.1. Các khái niệm key

- **Symmetric key:** cùng key dùng mã hóa và giải mã; hiệu năng phù hợp nhiều workload dữ liệu.
- **Asymmetric key pair:** public/private key dùng cho ký/verify hoặc mã hóa/giải mã theo thuật toán.
- **DEK:** key mã hóa payload/data.
- **KEK/wrapping key:** key dùng để bọc DEK.
- **Root/master key:** key cấp cao bảo vệ các key khác hoặc tạo hierarchy theo thiết kế.
- **Signing key:** key ký artifact, token, message hoặc certificate.

Không dùng một key cho mọi mục đích. Key separation và algorithm/key usage giúp giảm rủi ro cross-purpose.

### 10.2. Envelope encryption

Thay vì dùng KMS gọi cho mỗi byte dữ liệu, ứng dụng có thể dùng envelope encryption:

1. KMS tạo hoặc bảo vệ KEK.
2. Ứng dụng lấy một DEK hoặc yêu cầu KMS tạo data key.
3. DEK mã hóa payload bằng thuật toán phù hợp.
4. DEK được bọc bằng KEK.
5. Lưu ciphertext, wrapped DEK, key ID và encryption metadata.
6. Khi decrypt, lấy quyền unwrap DEK qua KMS rồi giải mã payload.

~~~mermaid
flowchart TB
    KMS["KMS / KEK"] -->|Wrap DEK| W["Wrapped DEK"]
    DATA["Plaintext data"] --> ENC["Authenticated encryption"]
    DEK["Data encryption key"] --> ENC
    ENC --> CT["Ciphertext"]
    W --> STORE[("Ciphertext + wrapped DEK + key metadata")]
    CT --> STORE
    STORE --> DEC["Decrypt with unwrapped DEK"]
    KMS -->|Unwrap DEK| DEC
    DEC --> OUT["Plaintext"]
~~~

Envelope encryption giảm số lần sử dụng KEK trên dữ liệu lớn và hỗ trợ key hierarchy. Cần lưu thuật toán, nonce/IV, authentication tag, key version và associated data theo format được xác định. Không tự thiết kế cryptographic primitive.

### 10.3. Authenticated encryption

Khi mã hóa dữ liệu ứng dụng, ưu tiên authenticated encryption mode được thư viện/chuẩn tin cậy hỗ trợ, chẳng hạn AES-GCM hoặc ChaCha20-Poly1305 khi phù hợp môi trường. Nonce phải dùng đúng quy tắc duy nhất cho mỗi key/mode. Nếu nonce reuse xảy ra trong một số mode, confidentiality và integrity có thể bị phá nghiêm trọng.

Không tự ghép encryption và MAC bằng code tùy ý hoặc dùng ECB cho dữ liệu ứng dụng.

## 11. Key policy và separation of duties

KMS policy cần tách quyền:

- Ai được tạo key?
- Ai được dùng key để encrypt?
- Ai được decrypt/unwrap?
- Ai được rotate?
- Ai được disable/revoke?
- Ai được thay policy/grant?
- Ai có thể schedule destruction?
- Ai có thể restore hoặc tạo replica key ở region khác?

Application runtime thường cần quyền sử dụng key cụ thể, không cần quyền quản trị key. Người vận hành có thể cần xem metadata nhưng không cần decrypt nội dung dữ liệu. Các thao tác disable/destroy nên có approval và guardrail phù hợp.

Root/CA key hoặc key bảo vệ dữ liệu critical có thể yêu cầu HSM, multi-person control hoặc dual authorization theo policy tổ chức.

## 12. Key rotation: đổi key mà vẫn đọc được dữ liệu cũ

Key rotation có ít nhất hai ý nghĩa:

1. Tạo key version mới cho thao tác mã hóa dữ liệu mới.
2. Re-encrypt dữ liệu cũ bằng DEK/key mới hoặc rewrap DEK hiện tại bằng KEK mới.

Hai việc này khác nhau. Trong envelope encryption, rotate KEK có thể chỉ cần unwrap DEK và wrap lại bằng KEK mới, không nhất thiết giải mã toàn bộ payload. Rotate DEK thường cần giải mã và mã hóa lại payload.

### 12.1. Rotation KEK và DEK

| Operation | Dữ liệu ciphertext | Wrapped DEK | Chi phí |
| --- | --- | --- | --- |
| Chỉ đổi key version cho encryption mới | Giữ nguyên ciphertext cũ | Metadata mới cho DEK mới | Thấp hơn |
| Rewrap DEK | Không đổi ciphertext nếu format hỗ trợ | Bọc lại bằng KEK mới | Thường thấp hơn full re-encryption |
| Rotate DEK/re-encrypt | Tạo ciphertext mới | DEK mới và wrapped DEK mới | Cao hơn, cần đọc/ghi dữ liệu |
| Disable/destroy old KEK quá sớm | Có thể không đọc được dữ liệu cũ | Không unwrap được DEK cũ | Rủi ro mất khả năng giải mã |

Lưu ý: nếu yêu cầu cryptographic erasure, cần loại bỏ khả năng truy cập key material theo quy trình có kiểm soát. Không destroy key chỉ vì đã tạo key version mới; phải xác minh không còn dữ liệu hoặc backup cần key cũ.

### 12.2. Versioned key metadata

Record mã hóa nên chứa key ID/version hoặc wrapped DEK metadata để biết cách giải mã. Không phụ thuộc vào một alias trỏ tới “current key” mà không lưu version lịch sử cần thiết. Alias có thể đổi, còn ciphertext cũ phải giữ được thông tin đủ để decrypt trong vòng đời retention.

## 13. Kế hoạch luân chuyển theo kiểu tài sản

| Tài sản | Cách rotation thường dùng | Điều cần xác minh |
| --- | --- | --- |
| Database password | Tạo user/credential mới, cập nhật pool, verify, revoke cũ | Connection cũ, transaction đang chạy, permission parity |
| API token | Tạo token thứ hai/overlap, deploy clients, revoke token cũ | Provider có overlap và quota token không |
| OAuth client secret | Thêm secret mới, cập nhật client, quan sát token issuance, retire cũ | Cached config và token lifetime |
| TLS certificate | Issue cert/key mới, deploy cohort, verify handshake, revoke nếu cần | SAN, chain, pinning, load balancer và client trust |
| mTLS workload cert | Cấp identity cert mới, cập nhật trust overlap, refresh workload | CA rotation, sidecar/cache và expiry |
| KMS KEK | Tạo version/key mới, chuyển encryption hoặc rewrap DEK | Backup, old ciphertext, cross-region key access |
| DEK | Re-encrypt data hoặc version per object/record | Throughput, integrity, rollback và metadata |
| Signing key | Phát hành public key mới, ký bằng private key mới, verify overlap, retire cũ | JWT/token lifetime, client trust và signature key ID |

Rotation không có overlap phải dùng một protocol cụ thể để tránh downtime. Ví dụ database hỗ trợ một password duy nhất có thể cần tạo user thứ hai rồi chuyển connection thay vì đổi password của cùng user.

## 14. Triển khai rotation không gián đoạn

Một workflow chung có thể gồm:

1. **Inventory:** tìm tất cả consumer, cache, connection pool, region và job đang dùng version cũ.
2. **Prepare:** tạo version mới, kiểm tra policy/permission và xác minh target chấp nhận.
3. **Overlap:** cho phép version mới và cũ cùng tồn tại trong thời gian ngắn nếu target hỗ trợ.
4. **Rollout:** cập nhật workload theo canary/cohort; refresh secret/certificate/key reference.
5. **Observe:** kiểm tra auth failure, handshake, error rate, connection và decrypt success.
6. **Commit:** xác nhận mọi consumer đã dùng version mới.
7. **Revoke:** vô hiệu version cũ ở source of authority.
8. **Verify revocation:** thử đảm bảo credential cũ bị từ chối và không còn consumer dùng nó.
9. **Close:** cập nhật inventory, audit và rotation timestamp.

### 14.1. Tránh cache giữ secret cũ

Ứng dụng có thể cache secret hoặc giữ connection pool lâu hơn TTL của secret. Cần cơ chế refresh trước expiry, invalidate theo version event hoặc restart/drain có kiểm soát. Không làm refresh đồng loạt mọi instance nếu secret manager có rate limit thấp; dùng jitter và staged rollout.

### 14.2. Rollback trong thời gian overlap

Nếu credential mới lỗi, có thể tạm quay về credential cũ khi nó chưa bị revoke và chưa có dấu hiệu compromise. Nếu rotation do lộ secret, không được rollback về credential đã bị lộ; cần forward fix với tài sản mới và giới hạn traffic.

## 15. Certificate CA rotation và trust transition

Rotate leaf certificate thường dễ hơn rotate CA. Khi CA/intermediate đổi, client có thể cần trust cả chain cũ và mới trong một khoảng chuyển tiếp.

Một quy trình trust transition:

1. Phát hành hoặc triển khai trust anchor/intermediate mới cho client.
2. Xác minh client tin cả chain cần thiết.
3. Chuyển server/client certificate sang chain mới theo cohort.
4. Theo dõi handshake và certificate validation.
5. Xác nhận không còn endpoint dùng chain cũ.
6. Gỡ trust anchor cũ theo kế hoạch.
7. Thu hồi certificate cũ nếu bị compromise.

Nếu gỡ CA cũ trước khi mọi endpoint/client chuyển xong, kết nối có thể thất bại diện rộng. Nếu giữ trust anchor đã compromise quá lâu, kẻ tấn công vẫn có thể tạo certificate được tin cậy. Thời gian overlap phải có deadline và monitoring.

## 16. Compromise response: nghi lộ secret hoặc key

Khi nghi ngờ credential/key bị lộ, ưu tiên ngăn truy cập tiếp tục và bảo toàn bằng chứng.

Quy trình khái niệm:

1. Xác định asset, scope quyền và thời gian nghi bị lộ.
2. Xác định workload, tenant, repo, log, endpoint và data đã có thể bị truy cập.
3. Disable/revoke hoặc thay thế theo mức độ nguy cấp.
4. Fence các session/token/connection còn hiệu lực nếu cơ chế hỗ trợ.
5. Cấp credential/key mới và rollout theo quy trình khẩn cấp.
6. Xoay các secret downstream có thể bị đọc từ credential bị lộ.
7. Kiểm tra audit log, API calls, database access và dữ liệu bị truy xuất/thay đổi.
8. Tìm dấu vết secret trong Git history, artifact, log và backup; xử lý theo retention/security policy.
9. Rotate dependent credentials và key nếu có khả năng bị compromise dây chuyền.
10. Xác minh credential cũ không còn dùng được, cập nhật incident record và cải thiện controls.

Không chỉ xóa secret khỏi file mới là đủ; giá trị đã commit vào Git history hoặc lưu trong artifact vẫn có thể bị truy cập. Khi secret xuất hiện công khai, phải coi là đã compromise cho tới khi được chứng minh ngược lại; rotate/revoke trước rồi làm sạch lịch sử theo policy.

### 16.1. Private key compromise

Khi private key TLS/signing bị lộ, cần đánh giá certificate/token đã được phát hành hoặc ký trong khoảng nào. Revoke certificate có thể cần CRL/OCSP hoặc cập nhật trust policy; thay key nhưng client vẫn trust CA/chain cũ không tự thu hồi certificate đã bị lộ.

Với signing key, cần quản lý key ID, verify key rotation và thời hạn token đã phát hành. Có thể cần revoke token/session hoặc rút ngắn trust window, tùy loại token.

## 17. Crypto-erasure và key destruction

Crypto-erasure là loại bỏ key material theo cách khiến ciphertext không thể giải mã bằng key đó nữa, khi các điều kiện kỹ thuật và chính sách cho phép. Đây có thể là biện pháp hỗ trợ xóa dữ liệu, nhưng cần thận trọng.

Trước khi destroy key, phải xác minh:

- Key có bảo vệ dữ liệu nào khác không?
- Có bản sao/replica/backup/archive nào còn cần key không?
- Có legal hold hoặc retention requirement không?
- Có key escrow/recovery material nào còn tồn tại?
- Operation có thể undo không?
- Ai phê duyệt và ai thực thi?
- Audit evidence ghi lại key ID, thời điểm và phạm vi nào?

Disable key có thể tạm ngăn sử dụng nhưng vẫn cho phép phục hồi; schedule destruction và destroy thực tế có semantics khác nhau. Không nhầm hai trạng thái. Một thao tác hủy key không thể phục hồi có thể làm mất dữ liệu vĩnh viễn.

## 18. Backup, restore và khả năng truy cập key

Backup ciphertext mà không có key hoặc không thể truy cập KMS/HSM tương ứng thì không phải một bản backup có thể phục hồi. DR plan cần bảo vệ đồng thời dữ liệu và khả năng giải mã.

Kiểm tra:

- Key có được replicate/replica ở region DR theo policy?
- KMS policy có cho phép recovery workload dùng key?
- Identity, role và network tới KMS có hoạt động trong DR?
- Key version cũ còn enabled trong suốt retention cần thiết?
- Backup metadata chứa key ID/version và algorithm?
- HSM quorum/backup key material có thể phục hồi theo quy trình?
- Restore test đã decrypt thành công bản dữ liệu thực tế chưa?

Nếu key thuộc region/account khác, failover compute sang region mới nhưng không có quyền truy cập key có thể làm ứng dụng không đọc được database hoặc object.

### 18.1. Recovery key và break-glass

Một số key critical cần quy trình break-glass tách biệt khỏi vận hành thường ngày. Quy trình này nên có dual control, thời hạn, audit, notification và hậu kiểm. Không lưu một bản master key trong wiki hoặc shared drive để “phòng trường hợp KMS lỗi”.

## 19. Audit, monitoring và alert

Secret/certificate/key cần được giám sát như tài nguyên production.

| Metric/Signal | Ý nghĩa |
| --- | --- |
| Secret age / last rotation | Credential đã tồn tại bao lâu |
| Expiry days | Số ngày còn lại của certificate/credential |
| Rotation success/failure | Rotation workflow có hoàn tất |
| Active version distribution | Workload đang dùng version nào |
| Secret read anomalies | Workload đọc secret bất thường |
| Access denied spikes | Policy hoặc identity/config có vấn đề |
| Certificate handshake failures | Chain, expiry, hostname hoặc key mismatch |
| KMS throttling/latency | Ảnh hưởng encryption/decryption path |
| Key disable/destroy events | Thao tác nhạy cảm cần audit |
| Decrypt failures | Metadata/key version hoặc quyền không đúng |
| Orphaned assets | Secret/key/certificate không còn owner/consumer |
| Revoked credential usage | Consumer vẫn cố dùng credential cũ |

Alert cần phân loại mức nghiêm trọng và gắn owner/runbook. Một certificate sắp hết hạn không có cùng urgency với event decrypt thất bại hàng loạt hoặc secret bị đọc từ workload lạ.

Không đưa plaintext, private key, token hoặc secret value vào metric label/log. Audit ghi asset ID, principal, action, result, time và context phù hợp; không ghi bí mật.

## 20. Cấu hình rotation và policy as code

Rotation policy nên được version hóa và kiểm tra như code/config khác. Ví dụ policy khái niệm:

~~~yaml
assetPolicy:
  type: databaseCredential
  owner: booking-platform
  maxAgeDays: 60
  access:
    workloadIdentity: booking-api-prod
    secretRef: production/booking/database
    operations:
      - read
  rotation:
    mode: staged
    overlapHours: 4
    verifyConnectionBeforeRevoke: true
  alerts:
    beforeExpiryDays: [14, 7, 2]
~~~

Đây là cấu trúc minh họa, không phải schema chuẩn. Policy thực tế phải xét khả năng target, TTL, secret manager, workload restart và yêu cầu business.

Policy-as-code có thể kiểm tra:

- Secret không được dùng chung trái policy.
- Certificate có SAN và expiry đạt chuẩn.
- Key sử dụng algorithm/key size được phê duyệt.
- Runtime identity không có quyền admin.
- Rotation policy có owner và thời hạn.
- Production secret không được tham chiếu từ staging.
- Key destruction cần approval và retention validation.

## 21. Ví dụ kiến trúc: API đặt thuê và payment connector

Một nền tảng SaaS có booking API, database, payment provider và ERP connector theo tenant.

### 21.1. Thiết kế tài sản

- Booking API dùng workload identity để lấy database credential có scope giới hạn.
- Database password được rotate theo hai-phase; connection pool refresh dần.
- API server certificate được certificate manager phát hành và tự động renew.
- Internal service communication dùng mTLS với workload identity certificate có TTL phù hợp.
- Payment connector secret tách theo tenant trong secret manager; runtime chỉ đọc secret của tenant đã được xác thực.
- Customer/payment-sensitive data được mã hóa bằng DEK; DEK được wrap bởi KEK trong KMS.
- Key ID/version được lưu cùng ciphertext metadata để decrypt lịch sử.
- KMS policy tách encrypt/decrypt khỏi key administration.
- Rotation/revocation có audit, alert và runbook.

~~~mermaid
flowchart TB
    APP["Booking API workload"] --> ID["Workload identity"]
    ID --> SM["Secret manager"]
    SM --> DBSEC["DB credential"]
    DBSEC --> DB[("Transactional database")]
    APP --> CERT["Certificate manager"]
    CERT --> TLS["TLS / mTLS identity"]
    APP --> KMS["KMS / HSM"]
    KMS --> KEK["KEK"]
    APP --> DEK["DEK for data"]
    DEK --> DATA["Encrypted data"]
    KEK --> WRAP["Wrapped DEK"]
    APP --> TRES["Tenant-scoped secret reference"]
    TRES --> SM
    SM --> PAY["Payment / ERP credentials"]
~~~

Sơ đồ cho thấy các thành phần khái niệm; thực tế application thường yêu cầu KMS tạo/wrap DEK thay vì đọc trực tiếp KEK plaintext. KMS/HSM nên giữ key material trong boundary của dịch vụ.

### 21.2. Kịch bản rotation database credential

1. Rotation worker xác thực bằng workload identity riêng.
2. Tạo database user B với quyền tương đương user A nhưng scope đúng.
3. Lưu credential B thành secret version mới.
4. Rollout Booking API theo cohort và tạo connection mới với B.
5. Theo dõi connection success, query error và transaction health.
6. Xác nhận không còn instance dùng A.
7. Revoke user A và thử xác thực để chắc chắn bị từ chối.
8. Cập nhật inventory/audit và xóa version cũ theo retention policy.

Nếu DB chỉ hỗ trợ một user password, cần dùng khả năng credential transition hoặc một account mới; đổi password trực tiếp khi connection cũ còn sống có thể gây lỗi khó kiểm soát.

### 21.3. Kịch bản certificate renewal

1. Certificate manager renew leaf certificate trước expiry.
2. Kiểm tra chain/SAN/key pair.
3. Deploy lên một instance canary.
4. Thực hiện handshake từ client và monitor error.
5. Rollout tới các instance/proxy còn lại.
6. Xác minh tất cả endpoint dùng certificate mới.
7. Revoke certificate cũ nếu cần; cập nhật inventory.

## 22. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Hardcode secret trong repository/image | Rò rỉ qua Git/artifact | Secret manager và workload identity |
| Dùng một credential cho nhiều service | Blast radius lớn, khó quy trách nhiệm | Identity/secret riêng theo workload |
| Lưu private key cạnh certificate trong bucket chung | Nhiều người có thể giả danh endpoint | KMS/HSM hoặc secret store với quyền chặt |
| Rotate store trước rồi revoke target ngay | Connection/consumer cũ lỗi | Overlap, staged rollout và verify |
| Chỉ tạo key version mới | Ciphertext cũ có thể vẫn phụ thuộc key cũ | Lập kế hoạch rewrap/re-encrypt và retention |
| Destroy KEK khi backup còn dùng | Không phục hồi được dữ liệu | Inventory dependency và restore test |
| Certificate renew nhưng không test chain | Client handshake thất bại | Canary handshake và trust-store validation |
| Tắt hostname verification | Mở cửa MITM | Sửa SAN/DNS/certificate chain đúng |
| Dùng feature/config cache cho secret lâu dài | Secret cũ còn hiệu lực không kiểm soát | TTL, version refresh và revoke |
| Ghi token/key vào log | Mở thêm bản sao bí mật | Redaction và secret scanning |
| Không theo dõi expiry | Certificate hết hạn gây outage | Inventory và alert trước expiry |
| Dùng chung key cho encryption/signing | Một compromise tác động nhiều chức năng | Key separation và usage policy |
| Runtime có quyền admin KMS | Workload có thể disable/destroy key | Least privilege, tách duties |
| Rotation không có owner | Credential quá hạn hoặc workflow bị bỏ dở | Owner, SLO và escalation |
| DR không có quyền truy cập KMS | Restore có ciphertext nhưng không decrypt được | DR identity/key access test |

## 23. Quy trình thiết kế và triển khai

1. **Inventory:** lập danh sách secret, certificate, private key, DEK/KEK và owner.
2. **Classify:** đánh giá impact, scope quyền, tenant/environment và retention.
3. **Chọn cơ chế quản lý:** secret manager, certificate manager, KMS/HSM theo loại tài sản.
4. **Thiết kế identity:** workload identity, audience, trust policy và least privilege.
5. **Thiết kế storage/reference:** không nhúng plaintext, version hóa và tách secret khỏi config.
6. **Định nghĩa lifecycle:** expiry, rotation cadence, emergency revoke, destruction và owner.
7. **Thiết kế rollout:** overlap, staged refresh, connection draining, verify và rollback window.
8. **Bảo vệ dữ liệu:** envelope encryption, metadata/version và key separation.
9. **Thiết kế certificate trust:** CA chain, SAN, mTLS, renewal và pinning transition.
10. **Thiết lập monitoring:** age, expiry, active version, failed auth, KMS latency và audit.
11. **Chuẩn bị incident:** compromise workflow, dependent secret rotation và forensic evidence.
12. **Kiểm thử DR:** restore ciphertext, truy cập key, verify certificate và dùng credential trong region phục hồi.
13. **Review định kỳ:** secret orphaned, version cũ, permission drift và key lifecycle.

## 24. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Rotation có overlap và rollback? Secret manager/KMS có HA? Certificate expiry và key dependency được theo dõi? DR restore đã decrypt thử? |
| **Bảo mật** | Workload identity và least privilege? Private key/secret có tập trung? Key usage tách? Audit và revoke có hiệu lực? |
| **Hiệu quả hiệu năng** | Secret retrieval/cache, KMS latency và connection refresh có ảnh hưởng request? Rotation có tạo load spike? |
| **Tối ưu chi phí** | KMS/HSM calls, certificate issuance, secret versions và storage có được kiểm soát? Mức bảo vệ phù hợp impact? |
| **Khả năng vận hành** | Inventory có owner? Rotation status, expiry, orphaned asset và incident runbook có quan sát được? |

### Checklist nghiệm thu

- [ ] Secret/certificate/key có inventory, owner, purpose, environment và classification.
- [ ] Plaintext không nằm trong source, image, frontend, log hoặc ticket.
- [ ] Runtime dùng workload identity với quyền đọc cụ thể.
- [ ] Secret manager tách quyền read, write, rotate, revoke và administer.
- [ ] Tenant/environment được scope riêng cho secret và connector credential.
- [ ] Certificate có SAN, trust chain, usage và expiry monitoring.
- [ ] TLS hostname verification được bật; mTLS identity gắn với authorization.
- [ ] KMS/HSM policy tách encrypt/decrypt khỏi key administration.
- [ ] DEK/KEK hierarchy và envelope metadata có version rõ.
- [ ] Rotation có staged rollout, overlap, verify và revoke old version.
- [ ] Cache/connection pool refresh trước expiry; có handling renew failure.
- [ ] Compromise response thu hồi token/session và kiểm tra dependent secrets.
- [ ] Key disable/destroy có approval, retention validation và audit.
- [ ] Backup/DR có quyền truy cập KMS/key và đã thử decrypt dữ liệu restore.
- [ ] Alert phát hiện credential quá hạn, version cũ và access bất thường.
- [ ] Rotation/restore/incident runbook có owner và đã diễn tập.

## 25. Bài tập áp dụng

Một nền tảng SaaS quản lý thuê thiết bị có 300 tenant. Mỗi tenant có thể kết nối một ERP và một cổng thanh toán riêng. Booking API dùng database credential tĩnh; API gateway có TLS certificate hết hạn sau 20 ngày; dữ liệu hồ sơ hợp đồng được mã hóa bằng DEK, các DEK được wrap bằng một KEK trong KMS. Một secret connector bị phát hiện trong log CI của một repository riêng tư.

Hãy thiết kế:

1. Phân loại secret, certificate, private key, DEK và KEK; xác định asset owner.
2. Thiết kế workload identity để Booking API chỉ đọc đúng database secret và connector secret theo tenant.
3. Quy trình ứng phó secret lộ trong CI log gồm revoke, rotation, audit và kiểm tra dependent credential.
4. Kế hoạch rotate DB credential không làm gián đoạn connection pool.
5. Kế hoạch renew TLS certificate và xác nhận chain/SAN trước khi rollout.
6. Làm sao rotate KEK và quyết định có cần rewrap DEK hay re-encrypt dữ liệu?
7. Dữ liệu/backup nào vẫn cần key cũ và khi nào mới được phép destroy?
8. Thiết kế alert cho certificate expiry, secret age, rotation failure và KMS access anomaly.
9. Kiểm thử DR ở region khác để chứng minh backup ciphertext có thể decrypt.
10. Những quyền nào cần dual control/break-glass và audit riêng?

Một phương án tốt sẽ thu hồi sớm secret đã lộ, tạo credential mới và triển khai theo tenant/cohort; tách connector secret theo tenant; renew certificate trước expiry với canary handshake; dùng envelope encryption và lưu key version metadata; chỉ retire KEK cũ sau khi xác minh dữ liệu và backup cần thiết đã được rewrap/re-encrypt hoặc hết retention.

**Điểm cốt lõi:** secret xác thực quyền truy cập, certificate thiết lập niềm tin về danh tính, còn encryption key bảo vệ dữ liệu hoặc chữ ký. Quản lý an toàn đòi hỏi inventory, workload identity, quyền tối thiểu, version, audit và quy trình thu hồi. Rotation chỉ hoàn tất khi consumer đã chuyển, phiên bản cũ bị vô hiệu có kiểm chứng và dữ liệu cũ vẫn phục hồi được theo chính sách.
