# Thiết kế HSM boundary

Một HSM boundary là ranh giới bảo mật xác định nơi key material được tạo, lưu giữ và sử dụng dưới sự kiểm soát của phần cứng mật mã chuyên dụng. Thiết kế boundary tốt phải trả lời rõ những thành phần nào nằm trong vùng bảo vệ của HSM, những thành phần nào chỉ được phép gọi operation qua API, identity nào được quyền gọi, dữ liệu nào được phép đi qua ranh giới và cách phát hiện hoặc ngăn việc lạm dụng quyền hợp lệ.

Case study này thiết kế ranh giới HSM cho một nền tảng thanh toán đa tenant. Hệ thống cần mã hóa dữ liệu giao dịch, bảo vệ khóa ký, hỗ trợ rotation và recovery, đồng thời vận hành được khi một thiết bị HSM hoặc một vùng triển khai gặp sự cố. Thiết kế tập trung vào việc giữ KEK và private signing key trong HSM, giới hạn quyền của ứng dụng, và làm rõ trường hợp DEK phải đi qua bộ nhớ ứng dụng trong mô hình envelope encryption.

HSM không tự động bảo vệ toàn bộ ứng dụng. HSM có thể ngăn key material bị trích xuất trực tiếp, nhưng một ứng dụng bị chiếm quyền vẫn có thể lạm dụng API Encrypt, Decrypt, Sign hoặc Unwrap mà identity của ứng dụng được phép gọi. Vì vậy, HSM boundary phải kết hợp phần cứng, network, workload identity, authorization theo tenant, key policy, operator control, audit, recovery và quy trình vận hành.

## 1. Bối cảnh case study

Một nền tảng thanh toán giả định xử lý giao dịch cho nhiều merchant. Các service lưu trữ thông tin giao dịch, token tham chiếu, dữ liệu đối soát và chứng từ. Một số dữ liệu cần mã hóa ở tầng ứng dụng để kiểm soát key theo tenant. Hệ thống cũng ký thông điệp trao đổi với đối tác và ký một số artifact nội bộ.

Các nhóm yêu cầu:

- Mỗi môi trường production, staging và development có trust domain riêng.
- Tenant không được sử dụng key của tenant khác.
- KEK và private signing key phải được tạo hoặc import theo ceremony được kiểm soát và không được export ở dạng plaintext.
- Ứng dụng chỉ gọi operation đã được cấp quyền; không có quyền quản trị HSM.
- Rotation phải hỗ trợ đọc dữ liệu cũ trong thời gian migration.
- Backup và recovery phải hoạt động khi một thiết bị hoặc một site không khả dụng.
- Audit phải truy vết được actor, key ID/version, operation, tenant và kết quả.
- Thay đổi policy, restore và destruction phải có approval phù hợp.
- HSM outage không được dẫn tới fallback âm thầm sang software key.

Các con số throughput, latency, RPO và RTO sẽ được xác định từ workload thực tế và hợp đồng vận hành. Case study không giả định một giá trị chung phù hợp cho mọi HSM.

## 2. Mục tiêu bảo mật và ranh giới tin cậy

Mục tiêu là giới hạn việc tiếp xúc trực tiếp với key material, giảm số principal có quyền sử dụng key, và làm cho mọi operation qua HSM có thể kiểm soát và kiểm toán.

Các tài sản cần bảo vệ:

- Tenant KEK dùng wrap/unwrap DEK.
- Private signing key dùng ký thông điệp.
- Key bảo vệ backup hoặc recovery package.
- HSM security domain, partition và operator credential.
- Policy, grant, key metadata và key version mapping.
- Audit evidence về việc sử dụng và quản trị key.
- Plaintext và DEK trong thời gian xử lý tại ứng dụng.

Trust boundary không chỉ là đường biên mạng. Nó gồm boundary phần cứng, identity, process, tenant authorization, control plane, data plane, administrative access và evidence storage.

## 3. Threat model

Thiết kế cần xem xét các mối đe dọa sau:

| Threat | Mục tiêu của attacker | Kiểm soát trọng tâm |
|---|---|---|
| Application RCE | Gọi Decrypt/Sign bằng quyền hợp lệ | Workload identity, tenant authorization, rate limit, anomaly detection |
| Credential theft | Giả mạo workload | Short-lived identity, mTLS, attestation, revoke session |
| Network interception | Đọc hoặc sửa request | Private network, TLS/mTLS, endpoint validation |
| Operator compromise | Thay policy hoặc export key | Separation of duties, quorum, PAM, audit độc lập |
| HSM admin misuse | Tạo principal hoặc thay partition | Dual control, restricted admin plane, ceremony |
| Malicious deployment | Đưa code gọi HSM trái phép | CI/CD controls, artifact signing, workload attestation |
| Backup theft | Lấy key backup hoặc recovery package | Encrypted backup, independent custody, quorum |
| Audit tampering | Xóa dấu vết | Append-only/WORM storage, independent collector |
| HSM outage | Ép hệ thống dùng key yếu hơn | Fail closed cho crypto-critical path, HA/DR |
| Cross-tenant bug | Dùng nhầm key tenant | Server-side tenant binding, AAD, negative tests |

Threat model cần phân biệt key extraction với key misuse. HSM có thể giữ private key không thể export nhưng vẫn ký dữ liệu do một service bị chiếm quyền gửi tới. Tương tự, KEK không rời HSM nhưng một attacker có quyền Unwrap có thể yêu cầu HSM unwrap nhiều DEK.

## 4. HSM boundary gồm những gì?

Ranh giới phần cứng của HSM thường bao gồm thiết bị, firmware và vùng lưu giữ/thi hành cryptographic operation được bảo vệ theo chứng nhận hoặc security model của nhà cung cấp. Key object có thể được đánh dấu sensitive và non-extractable theo khả năng của thiết bị.

Các thành phần thường nằm ngoài boundary phần cứng:

- Ứng dụng nghiệp vụ.
- Crypto gateway hoặc key service.
- SDK, JCA provider hoặc PKCS#11 client library.
- Host operating system và container runtime.
- Network switch, firewall và load balancer.
- CI/CD, secrets delivery và deployment controller.
- Operator workstation và privileged access system.
- Audit collector và SIEM.

Một số cloud HSM có boundary vật lý do provider vận hành; tổ chức kiểm soát partition, identity và policy theo dịch vụ. Một số HSM on-premises cho phép tổ chức kiểm soát thiết bị, phòng máy, network và ceremony. Cần đọc security boundary và shared-responsibility model của đúng sản phẩm.

Không được mô tả PKCS#11 client library hoặc ứng dụng là nằm bên trong HSM boundary chỉ vì chúng gọi HSM. Chúng là thành phần bên ngoài gửi request qua giao diện được kiểm soát.

## 5. Phân vùng trust zone

Case study chia hệ thống thành các vùng:

| Zone | Thành phần | Mức tin cậy và kiểm soát |
|---|---|---|
| Z0 | Merchant, partner và internet client | Không tin cậy; xác thực ở edge |
| Z1 | API gateway và ingress | Chặn request, xác thực client, rate limit |
| Z2 | Payment application | Xử lý nghiệp vụ, không có quyền HSM admin |
| Z3 | Crypto gateway | Workload identity, tenant authorization, operation allowlist |
| Z4 | HSM client network | Private endpoint, mTLS hoặc cơ chế xác thực của provider |
| Z5 | HSM device/cluster | Key object, crypto engine, partition và HSM policy |
| Z6 | Admin/custody plane | PAM, operator identity, quorum và ceremony |
| Z7 | Audit/evidence plane | Collector độc lập, immutable storage và restricted read |

Z3 là một lớp trung gian hữu ích khi nhiều ứng dụng cần dùng chung HSM. Nó thực thi authorization theo tenant và business context trước khi gọi HSM. Tuy nhiên, crypto gateway cũng trở thành thành phần có đặc quyền cao; cần harden, phân tách workload, kiểm thử và giám sát chặt chẽ.

## 6. Sơ đồ kiến trúc tổng thể

~~~~mermaid
flowchart TB
    C[Merchant and partner clients]
    G[API gateway]
    A[Payment application]
    X[Crypto gateway]
    HN[Private HSM network]
    subgraph HB[HSM deployment zone]
        H1[HSM node A]
        H2[HSM node B]
        P[Partitions and key objects]
        H1 --- P
        H2 --- P
    end
    subgraph AP[Administrative plane]
        PAM[Privileged access management]
        O[Independent operators and custodians]
    end
    subgraph EP[Evidence plane]
        COL[Audit collector]
        W[Immutable audit store]
        SIEM[SIEM and incident response]
    end
    C --> G --> A --> X --> HN
    HN --> H1
    HN --> H2
    PAM --> O
    O --> H1
    O --> H2
    H1 --> COL
    H2 --> COL
    X --> COL
    COL --> W --> SIEM
~~~~

Ứng dụng không kết nối trực tiếp tới administrative interface. Crypto gateway dùng endpoint dành cho crypto operation; operator dùng một đường quản trị riêng. Audit được chuyển sang evidence plane độc lập để người vận hành HSM không thể âm thầm xóa toàn bộ dấu vết.

Subgraph HSM trong sơ đồ biểu diễn deployment/management zone của cluster. Mỗi HSM module vật lý có security boundary riêng theo chứng nhận và security model của thiết bị; cluster hoặc partition không tự động trở thành một FIPS boundary duy nhất bao quanh mọi node.

## 7. Ranh giới control plane và data plane

**Data plane** thực hiện operation trên key: Encrypt, Decrypt, Sign, Verify, Wrap và Unwrap. **Control plane** quản lý key object, policy, partition, role, grant, rotation, backup, restore và destruction.

Phân tách hai plane giúp giảm quyền của workload:

- Payment application chỉ gọi business API được công bố.
- Crypto gateway chỉ gọi một allowlist operation trên key cụ thể.
- Key administrator quản lý metadata/policy theo quy trình.
- HSM custodian tham gia backup, restore và ceremony.
- Security approver phê duyệt thay đổi đặc quyền.
- Auditor đọc evidence nhưng không có quyền thay key policy.

Không cấp quyền quản trị HSM cho runtime workload chỉ để ứng dụng có thể lấy key handle. Key handle hoặc alias được resolve trong service theo registry đã xác thực.

## 8. Key hierarchy cho nền tảng thanh toán

Một hierarchy tham khảo:

~~~~mermaid
flowchart TD
    R[HSM internal master/security domain]
    K1[Tenant KEK A version 3]
    K2[Tenant KEK B version 2]
    D1[DEK for payment object A]
    D2[DEK for settlement object A]
    D3[DEK for payment object B]
    S[Payment signing private key]
    B[Backup protection key]
    R --> K1
    R --> K2
    R --> S
    R --> B
    K1 --> D1
    K1 --> D2
    K2 --> D3
~~~~

Giải thích:

- HSM internal master/security domain bảo vệ key object theo cơ chế nội bộ của thiết bị; không nhất thiết là key mà ứng dụng gọi trực tiếp.
- Tenant KEK dùng wrap/unwrap DEK của tenant tương ứng.
- DEK mã hóa dữ liệu bằng authenticated encryption như AES-256-GCM.
- Signing private key dùng riêng cho mục đích ký; không tái sử dụng làm KEK.
- Backup protection key thuộc recovery domain và có custody riêng.

Các mũi tên từ HSM security domain trong sơ đồ biểu diễn quan hệ bảo vệ và quản lý key object theo mô hình triển khai. Chúng không khẳng định internal master key trực tiếp wrap từng tenant KEK, signing key hoặc backup key bằng cùng một cơ chế trên mọi vendor. Phải dùng tài liệu security domain và backup semantics của thiết bị cụ thể để mô tả quan hệ thực tế.

Không dùng một KEK chung cho mọi tenant nếu yêu cầu isolation đòi hỏi key riêng. Nếu số lượng tenant quá lớn, có thể dùng hierarchy theo tenant group hoặc domain, nhưng phải phân tích blast radius và khả năng rewrap khi một tenant rời hệ thống.

## 9. Phân loại key và vị trí lưu giữ

| Key | Vị trí | Có export plaintext? | Ai sử dụng |
|---|---|---|---|
| HSM internal master key | Bên trong HSM | Không qua API thông thường | Firmware/security domain |
| Tenant KEK | HSM key object | Không | Crypto gateway qua Wrap/Unwrap |
| Signing private key | HSM key object | Không | Signing service qua Sign |
| DEK | Bộ nhớ xử lý ngắn hạn hoặc HSM object tùy mô hình | Có thể tồn tại tạm trong app ở mô hình envelope client-side | Crypto service |
| Public verification key | Registry/certificate store | Có | Application/verifier |
| Backup wrapping key | Recovery HSM/security domain | Theo cơ chế backup được kiểm soát | Custodian/restore workflow |

Điểm quan trọng là boundary của KEK và boundary của DEK có thể khác nhau. Với envelope encryption phía client, plaintext DEK thường phải xuất hiện trong memory của crypto service để mã hóa dữ liệu. Thiết kế phải công khai rủi ro này và giới hạn process có thể nhìn thấy DEK.

## 10. Chọn mô hình xử lý dữ liệu

Có hai mô hình chính:

| Mô hình | Cách làm | Ưu điểm | Chi phí/rủi ro |
|---|---|---|---|
| HSM xử lý payload | HSM giữ DEK và thực hiện Encrypt/Decrypt | DEK không đi vào application memory | Throughput, payload size, latency và session capacity phụ thuộc thiết bị |
| Envelope encryption | Ứng dụng dùng DEK; HSM bảo vệ KEK để wrap/unwrap | Phù hợp payload lớn và scale ứng dụng | DEK plaintext tồn tại tạm trong crypto service |

Case study chọn envelope encryption cho dữ liệu giao dịch lớn và HSM-held signing key cho operation ký. Crypto gateway là nơi duy nhất được phép xử lý DEK plaintext. Với dữ liệu nhỏ hoặc operation có yêu cầu non-extractable DEK nghiêm ngặt, có thể dùng HSM thực hiện trực tiếp crypto operation nếu hiệu năng và provider hỗ trợ.

Không tuyên bố envelope encryption giữ DEK hoàn toàn trong HSM khi ứng dụng nhận plaintext DEK từ Unwrap. Đó là một boundary crossing có chủ đích.

## 11. Data flow: mã hóa dữ liệu

Quy trình Encrypt:

1. API gateway xác thực caller và chuyển identity context đã xác minh.
2. Payment application xác định tenant và object từ dữ liệu server-side.
3. Crypto gateway kiểm tra caller, tenant, purpose và quyền Encrypt.
4. Crypto gateway tạo DEK ngẫu nhiên bằng CSPRNG trong process được harden.
5. DEK mã hóa payload bằng AES-256-GCM với nonce duy nhất cho key.
6. Crypto gateway gửi DEK tới HSM để Wrap bằng tenant KEK version đã resolve.
7. HSM trả wrapped DEK (EDK); KEK không rời HSM.
8. Hệ thống lưu ciphertext, nonce, authentication tag, EDK, key ID/version và encryption context.
9. Crypto gateway xóa tham chiếu DEK và thực hiện best-effort zeroization nếu API cho phép.
10. Audit event ghi operation, principal, tenant, key ID/version và outcome.

Zeroization trong managed runtime như Java chỉ là best effort; garbage collector, heap copy và provider implementation có thể giữ bản sao. Không tuyên bố đã xóa vật lý mọi bản sao chỉ vì gọi Arrays.fill trên một byte array.

~~~~mermaid
sequenceDiagram
    participant App as Payment application
    participant CG as Crypto gateway
    participant H as HSM
    participant DB as Encrypted storage
    App->>CG: Encrypt(tenant, object, plaintext)
    CG->>CG: Authorize tenant and purpose
    CG->>CG: Generate random DEK
    CG->>CG: AES-GCM encrypt with AAD
    CG->>H: Wrap DEK with tenant KEK
    H-->>CG: Wrapped DEK
    CG->>DB: Store ciphertext, nonce, tag, EDK and key reference
    CG-->>App: Object reference
    CG->>CG: Best-effort clear DEK buffer
~~~~

## 12. Data flow: giải mã dữ liệu

Quy trình Decrypt:

1. Application yêu cầu đọc object và cung cấp business authorization context.
2. Crypto gateway lấy tenant/object identity từ registry và storage metadata đã xác thực.
3. Gateway kiểm tra caller có quyền đọc object và dùng key purpose tương ứng.
4. Gateway resolve đúng KEK ID/version; không dùng alias chưa được xác minh.
5. Gateway gửi EDK tới HSM để Unwrap.
6. Trong mô hình envelope client-side, DEK plaintext được trả về crypto gateway trong memory.
7. Gateway kiểm tra encryption context và dùng AES-GCM để xác minh tag trước khi trả plaintext.
8. Nếu authentication tag sai, tenant mismatch hoặc AAD mismatch, từ chối và không trả plaintext.
9. Audit ghi Decrypt/Unwrap, actor, resource, outcome và request reference.
10. Gateway best-effort xóa DEK buffer và kết thúc session.

HSM bảo vệ KEK khỏi export trực tiếp, nhưng không thể ngăn một crypto gateway bị chiếm quyền sử dụng DEK plaintext đã nhận. Do đó, process này phải có isolation, memory protection, least privilege, patching, runtime monitoring và network egress restriction.

## 13. Encryption context và tenant binding

Mỗi encrypted object cần metadata đủ để giải mã đúng context:

- tenant ID.
- object ID hoặc record ID.
- purpose.
- algorithm và format version.
- KEK ID/version.
- DEK wrapping mechanism.
- AEAD nonce và authentication tag.
- Ciphertext reference.

AAD của AES-GCM nên bind các thuộc tính như tenant ID, object ID, purpose và schema version theo encoding canonical. AAD không bí mật nhưng phải được xác thực. Không lấy tenant ID từ header do caller tự gửi rồi tin tuyệt đối; gateway phải resolve tenant từ authorization context.

Nếu ciphertext của tenant A bị copy sang tenant B, AAD mismatch phải làm authentication fail. Test phải kiểm tra cả swap object, swap tenant, swap purpose và sửa key version metadata.

## 14. Network boundary

HSM client endpoint chỉ được truy cập từ crypto gateway hoặc workload được phê duyệt.

Kiểm soát mạng:

- Đặt HSM trên private subnet hoặc network segment chuyên dụng.
- Không expose HSM management interface ra internet.
- Dùng firewall/security group allowlist theo source workload và port cần thiết.
- Tách crypto traffic khỏi admin traffic.
- Dùng TLS/mTLS nếu endpoint và vendor protocol hỗ trợ; xác minh certificate và hostname.
- Không tắt certificate validation để xử lý lỗi kết nối.
- Hạn chế egress từ crypto gateway.
- Ghi flow log và cảnh báo kết nối từ source lạ.
- Dùng private connectivity hoặc dedicated link khi mô hình triển khai yêu cầu.
- Có quy trình rotation certificate cho HSM client channel.

Network segmentation không thay thế authentication và authorization ở HSM. Một host nằm trong subnet được phép vẫn phải xác thực bằng identity và chỉ được gọi đúng operation.

## 15. Workload identity và authorization

Mỗi crypto gateway instance cần identity riêng hoặc identity workload có thể truy vết. Tránh dùng một PIN, password hoặc API credential chia sẻ cho toàn bộ application fleet.

Authorization phải xét:

- workload identity đã xác thực.
- tenant được phép phục vụ.
- key ID/version và purpose.
- operation được phép: Wrap, Unwrap, Sign...
- environment và security domain.
- request rate và batch limit.
- incident state hoặc key lifecycle state.
- approval reference với control-plane operation.

Không cho phép caller gửi một key alias bất kỳ rồi gateway thực hiện operation. Gateway phải map business purpose và tenant sang immutable key ID/version từ registry authoritative.

## 16. HSM partition và tenant isolation

Partition là cơ chế phân vùng tài nguyên/quyền trong HSM, nhưng semantics khác nhau theo vendor và model.

Một chiến lược:

- Partition riêng cho production và non-production.
- Partition riêng cho signing/CA hoặc key có blast radius đặc biệt nếu cần.
- Tenant KEK riêng trong partition production theo policy.
- Role operator, crypto user và auditor tách biệt.
- Giới hạn session và operation theo partition.
- Key object có label/attribute theo inventory; label không thay thế authorization.
- Không dùng chung operator credential giữa môi trường.

Không nhất thiết tạo một partition cho mỗi tenant. Quyết định phụ thuộc giới hạn thiết bị, quản trị, isolation requirement, quota và khả năng phục hồi. Nếu dùng chung partition, phải chứng minh tenant authorization được enforcement ở gateway và key policy, đồng thời có test cross-tenant denial.

## 17. Key generation, import và non-exportability

Key nhạy cảm nên được tạo bên trong HSM khi provider hỗ trợ. Key object cần thuộc tính phù hợp với mục đích:

- Sensitive.
- Non-extractable.
- Chỉ cho phép operation cần thiết.
- Không cho phép derive hoặc wrap nếu không cần.
- Có key usage và algorithm constraint.
- Có owner, purpose, tenant và version trong registry.
- Có lifecycle state và cryptoperiod.

Nếu phải import key material, dùng quy trình custody được phê duyệt, xác minh nguồn, integrity, key check value hoặc mechanism tương ứng theo vendor. Không truyền key qua email, ticket, clipboard hoặc shell history.

Non-extractable là thuộc tính của HSM/provider và key object; cần xác minh semantics, không suy ra từ việc application chỉ nhận một object kiểu PrivateKey. Test phải thử export path bị từ chối theo policy và kiểm tra key attribute từ HSM management interface.

## 18. Operator và administrative boundary

Administrative plane cần được cô lập khỏi runtime crypto traffic.

Các kiểm soát:

- Operator dùng danh tính cá nhân, MFA và PAM.
- Tách Security Officer, Crypto Officer, Crypto User và Auditor theo vendor role.
- Dùng dual control/quorum cho security domain initialization, backup, restore và thao tác critical.
- Không chia sẻ smart card, PIN hoặc token.
- Ghi nhận ceremony participants, device, firmware, operation và thời điểm.
- Session admin có thời hạn, được ghi log và review.
- Break-glass có scope và TTL.
- Operator không có quyền đọc plaintext business data qua application.
- Auditor đọc log nhưng không có quyền thay key object hoặc policy.

Approval workflow ở ứng dụng không thay thế quorum enforcement bên trong HSM. Với operation mà HSM yêu cầu nhiều custodian, phải duy trì kiểm soát đó ở thiết bị.

## 19. HSM backup và disaster recovery

HA và backup là hai mục tiêu khác nhau. HSM cluster có thể chịu lỗi một node nhưng không đảm bảo phục hồi khi mất toàn bộ security domain, site hoặc credential custody.

Thiết kế recovery:

- Có HSM node ở failure domain khác nhau theo kiến trúc được vendor hỗ trợ.
- Xác minh key replication semantics: synchronous, asynchronous hay không tự động.
- Tạo secure HSM backup theo cơ chế vendor.
- Bảo vệ backup bằng security domain/backup key phù hợp.
- Lưu backup ở vị trí và account tách biệt.
- Dùng quorum/split knowledge cho recovery material.
- Giữ manifest, version, device compatibility và custody record.
- Kiểm thử restore trên thiết bị hoặc môi trường phục hồi tương thích.
- Định kỳ thực hiện recovery drill và đo thời gian.
- Kiểm tra backup của key policy, partition mapping và metadata registry.

Không copy raw HSM storage file như backup nếu vendor không hỗ trợ. Không giả định HSM replication đồng nghĩa backup độc lập hoặc có thể restore sang model khác.

## 20. Rotation và lifecycle

Key version phải được quản lý rõ ràng. Khi tạo KEK mới:

1. Tạo version mới trong HSM.
2. Kiểm tra key attributes, policy và owner.
3. Cập nhật registry với immutable key ID/version.
4. Cho phép new writes dùng KEK mới.
5. Tiếp tục unwrap dữ liệu cũ bằng KEK version cũ trong thời gian migration.
6. Rewrap EDK theo batch có checkpoint và idempotency.
7. Kiểm tra backup, archive, replica và DR.
8. Chuyển key cũ sang trạng thái không dùng cho new writes.
9. Chỉ schedule deletion sau dependency, retention và approval gate.

Signing key rotation có flow riêng: phát hành public key/certificate mới, cập nhật trust và verifier, lưu public key cũ cho verify lịch sử theo policy, rồi xử lý private key cũ theo retention và evidence requirements.

Không disable KEK cũ ngay sau khi tạo KEK mới nếu còn EDK hoặc backup cần unwrap bằng key cũ.

## 21. Audit và evidence

Audit phải có ít nhất hai lớp:

- HSM/provider audit ghi operation và administrative event mà thiết bị/provider quan sát.
- Crypto gateway audit ghi business context như tenant, object reference, request ID và authorization decision.

Các field nên liên kết:

- actor/workload identity.
- request ID, trace ID và correlation ID.
- provider operation ID.
- HSM cluster, partition và key ID/version.
- operation và outcome.
- tenant/purpose.
- policy version và approval reference.
- source endpoint và thời điểm.
- key lifecycle state.

Không log key bytes, PIN, token, plaintext hoặc full DEK. Audit collector và evidence store nên độc lập với HSM administrator; dùng append-only hoặc immutable storage khi phù hợp. Kiểm tra clock synchronization và ghi rõ event time/ingest time.

## 22. Monitoring và operational signals

Các tín hiệu cần theo dõi:

- HSM node availability, health và tamper alarm.
- Session exhaustion, login failure và operation latency.
- Wrap/unwrap/sign/decrypt volume theo principal, key và tenant.
- Authorization denied tăng đột biến.
- Key policy, partition hoặc role thay đổi.
- Operator login và ceremony ngoài lịch.
- Backup age, backup failure và restore drill result.
- Rotation backlog và key version cũ còn được dùng.
- Network connection từ source không nằm allowlist.
- Audit ingestion lag, gap và integrity failure.
- HSM failover và error rate theo mechanism.

Alert phải phân biệt lỗi thiết bị, lỗi client, policy denial, capacity saturation và nghi ngờ compromise. Không tự động failover sang software key khi HSM lỗi.

## 23. Performance và capacity planning

HSM có giới hạn session, operation rate, key object count và algorithm support. Capacity test cần dùng workload thực tế:

- Phân biệt Wrap/Unwrap, Sign/Verify và bulk Encrypt/Decrypt.
- Đo p50/p95/p99 latency.
- Đo throughput khi concurrency tăng.
- Kiểm tra session pool và reconnect.
- Test batch size và backpressure.
- Đo failover khi một node ngừng hoạt động.
- Kiểm tra rate limit theo tenant.
- Test queue saturation và timeout.
- Đánh giá tác động của audit logging.
- Xác định headroom cho rotation, recovery và incident response.

Không tối ưu bằng cách cache plaintext KEK hoặc private key. Có thể cache metadata, certificate/public key và mapping đã xác thực. Nếu cache DEK, phải có TTL, memory isolation, scope, invalidation và risk acceptance rõ ràng.

## 24. Java 17: kết nối signing key qua SunPKCS11

Ví dụ sau minh họa cách Java JCA truy cập private key trong token PKCS#11. Private key được lấy dưới dạng provider-backed key object; ứng dụng không đọc raw private key bytes.

~~~~java
import java.security.Key;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Provider;
import java.security.Security;
import java.security.Signature;
import java.util.Arrays;

public final class HsmSigningExample {
    public interface CredentialProvider {
        char[] readHsmPin();
    }

    private HsmSigningExample() {
    }

    public static byte[] sign(
            String pkcs11ConfigPath,
            String keyAlias,
            byte[] payload,
            CredentialProvider credentialProvider
    ) throws Exception {
        Provider base = Security.getProvider("SunPKCS11");
        if (base == null) {
            throw new IllegalStateException("SunPKCS11 provider is unavailable");
        }

        Provider hsmProvider = base.configure(pkcs11ConfigPath);
        if (Security.getProvider(hsmProvider.getName()) == null) {
            Security.addProvider(hsmProvider);
        }

        char[] pin = credentialProvider.readHsmPin();
        try {
            KeyStore token = KeyStore.getInstance("PKCS11", hsmProvider);
            token.load(null, pin);

            Key key = token.getKey(keyAlias, null);
            if (!(key instanceof PrivateKey privateKey)) {
                throw new IllegalStateException("HSM signing key was not found");
            }

            Signature signature = Signature.getInstance(
                    "SHA256withRSA",
                    hsmProvider
            );
            signature.initSign(privateKey);
            signature.update(payload);
            return signature.sign();
        } finally {
            Arrays.fill(pin, '\0');
        }
    }
}
~~~~

Các điều kiện khi áp dụng:

- Đường dẫn cấu hình PKCS#11 do administrator quản lý và không lấy từ request.
- Vendor library, firmware và JCA provider version phải tương thích.
- Key alias được resolve từ registry tin cậy.
- PIN lấy từ credential provider/PAM phù hợp, không hardcode trong source hoặc image.
- Key object phải được tạo với attributes phù hợp, bao gồm non-extractable theo provider.
- Algorithm SHA256withRSA chỉ là ví dụ; chọn mechanism đúng với key type và crypto policy.
- HSM/provider phải thực sự thực hiện operation; không âm thầm fallback sang provider software.
- Kiểm tra provider behavior, session lifecycle, login/logout và error semantics trên HSM test environment.

Xóa mảng PIN là best effort trong Java. Credential provider, native library hoặc JVM có thể tạo bản sao nội bộ; cần giảm thời gian sống và quyền truy cập của credential ở các lớp đó.

## 25. Crypto gateway API và policy gate

Không để business application gọi PKCS#11 trực tiếp. Gateway nên cung cấp API business-level giới hạn operation.

Ví dụ contract:

~~~~text
WrapDataKey(
  tenantId,
  purpose,
  keyVersion,
  plaintextDataKey,
  requestId
) -> wrappedDataKey

UnwrapDataKey(
  authenticatedWorkload,
  tenantId,
  purpose,
  keyVersion,
  wrappedDataKey,
  objectContext,
  requestId
) -> plaintextDataKey

Sign(
  authenticatedWorkload,
  signingKeyId,
  signingKeyVersion,
  messageDigest,
  requestId
) -> signature
~~~~

Gateway phải:

- Xác minh workload identity từ channel đã xác thực.
- Resolve tenant và object từ server-side authorization context.
- Allowlist operation theo service.
- Kiểm tra key state, purpose, version và algorithm.
- Áp dụng quota, rate limit và request size limit.
- Ghi audit decision trước/sau operation theo policy.
- Không trả key handle nội bộ hoặc HSM admin metadata cho caller.
- Chặn caller sửa key ID/version tùy ý.
- Có idempotency và reconciliation cho operation bất đồng bộ.

Unwrap API là API nhạy cảm. Không chỉ kiểm tra caller có quyền tới HSM; phải kiểm tra caller có quyền đọc object cụ thể thuộc tenant đó.

## 26. Failure mode và failover

| Failure | Hành vi mong muốn |
|---|---|
| HSM node down | Chuyển sang node còn khỏe theo cluster policy đã kiểm thử |
| Toàn bộ HSM unavailable | Từ chối hoặc queue có kiểm soát; không dùng software key thay thế |
| Client session expired | Re-authenticate và retry theo idempotency policy |
| Provider timeout | Reconcile operation ID trước khi retry |
| Key version missing | Fail closed, cảnh báo inventory mismatch |
| Unwrap denied | Không thử KEK khác một cách tự động |
| Audit sink unavailable | Durable buffer hoặc dừng operation nhạy cảm theo policy |
| HSM tamper alarm | Cô lập theo vendor runbook và incident response |
| Backup restore mismatch | Dừng recovery, preserve evidence và điều tra |
| Clock skew | Gắn timestamp quality flag, không làm mất event |

Fallback sang software key làm thay đổi trust boundary và security property. Nếu business yêu cầu degraded mode, phải thiết kế một key domain thay thế độc lập, approval, audit, data compatibility và explicit failover decision từ trước.

## 27. Case: ứng dụng bị chiếm quyền nhưng HSM không bị trích xuất key

Giả sử attacker chiếm được một container payment service. HSM private signing key vẫn non-extractable và KEK không thể export. Tuy nhiên, container có workload identity hợp lệ và crypto gateway cho phép Sign hoặc Unwrap.

Các biện pháp containment:

1. Revoke workload identity/session.
2. Chặn network source và isolate workload.
3. Tạm dừng operation bất thường theo principal/key/tenant.
4. Bảo toàn HSM, gateway, IAM và deployment audit.
5. Xác định operation Sign/Unwrap/Decrypt thành công trong time window.
6. Xác định dữ liệu hoặc thông điệp có thể đã bị truy cập/tạo.
7. Kiểm tra policy/grant và credential issuance.
8. Phát hành identity mới sau khi loại bỏ nguyên nhân.
9. Rotation/rekey nếu key hoặc trust domain bị ảnh hưởng.
10. Xác minh principal cũ bị từ chối và không còn session.

Bài học: HSM giảm nguy cơ key extraction nhưng không tự ngăn misuse qua API. Authorization phải gắn với tenant, object, purpose và business request.

## 28. Case: HSM site outage và recovery

Một site mất kết nối với toàn bộ HSM node. Hệ thống chuyển traffic tới failure domain còn lại nếu cluster topology và provider support cho phép. Nếu security domain không còn khả dụng, recovery team sử dụng backup theo ceremony đã định nghĩa.

Các bước:

- Xác định phạm vi outage và trạng thái key object.
- Không tự tạo key mới cùng alias để thay thế key cũ.
- Kiểm tra backup manifest, key version, device compatibility và custody.
- Đạt quorum custodian và approval.
- Restore trong partition/security domain phù hợp.
- Xác minh key attributes, key ID mapping và test operation.
- Đối soát audit và inventory.
- Mở lại traffic theo canary.
- Kiểm tra khả năng decrypt dữ liệu lịch sử và verify chữ ký cũ.

Recovery test cần chứng minh cả key material và metadata/policy/registry mapping được khôi phục. Có key nhưng mất mapping tới ciphertext version vẫn có thể làm dữ liệu không đọc được.

## 29. Test strategy cho HSM boundary

Test phải bao phủ cả boundary enforcement và behavior khi có lỗi.

| Test | Kết quả mong đợi |
|---|---|
| App không có HSM network route | Connection bị từ chối |
| Workload identity không hợp lệ | Gateway/HSM từ chối |
| Cross-tenant unwrap | Denied, không trả DEK |
| Wrong object AAD | AEAD authentication fail |
| Key alias substitution | Resolve immutable ID/version hoặc reject |
| Export non-extractable KEK | HSM từ chối |
| Runtime gọi admin API | IAM/network/HSM role từ chối |
| Operator đơn lẻ thực hiện ceremony cần quorum | HSM/workflow từ chối |
| HSM node failover | Operation tiếp tục theo HA policy |
| Toàn bộ HSM unavailable | Không fallback âm thầm |
| Old KEK sau rotation | Chỉ được dùng theo historical unwrap policy |
| Key policy tampering | Alert và approval gate |
| Audit sink outage | Buffer/fail behavior đúng policy |
| HSM backup restore | Key và metadata được xác minh |
| HSM tamper alarm | Incident/runbook được kích hoạt |
| High concurrency | Không vượt capacity và không mất audit |
| Session expiry | Re-authenticate an toàn |
| Duplicate request | Idempotent/reconcile đúng |
| Signing key isolation | Chỉ signing service được Sign |
| Software provider fallback | Test phát hiện và fail nếu policy cấm |

Ngoài test chức năng, cần penetration test network boundary, workload identity, operator plane, gateway authorization và CI/CD path. Test HSM thật phải dùng partition/account thử nghiệm, key test và dữ liệu giả.

## 30. Quyết định kiến trúc và trade-off

| Quyết định | Lý do | Trade-off |
|---|---|---|
| Giữ KEK trong HSM | Giảm nguy cơ export key wrapping | Phụ thuộc HSM availability/capacity |
| Envelope encryption cho payload lớn | Tách bulk crypto khỏi HSM throughput | DEK xuất hiện trong memory gateway |
| Crypto gateway trung tâm | Authorization/audit nhất quán | Gateway là high-value component |
| Partition theo environment/domain | Giảm blast radius | Tăng vận hành và quota |
| Tenant KEK riêng | Tenant isolation và crypto erasure granularity | Nhiều key object và rotation work |
| Separate admin plane | Ngăn runtime credential quản trị HSM | Cần vận hành PAM/custody riêng |
| Immutable audit store | Chống sửa/xóa evidence | Chi phí lưu trữ và truy xuất |
| No silent software fallback | Giữ nguyên trust boundary | Availability phụ thuộc HSM/DR |

Mỗi quyết định cần được ghi thành architecture decision record với threat model, owner, assumptions, failure mode và tiêu chí xem xét lại.

## 31. Lộ trình triển khai

Một rollout có thể chia thành các giai đoạn:

1. Inventory key, workload, tenant và operation hiện tại.
2. Chốt threat model, trust zone và key hierarchy.
3. Thiết lập HSM security domain, partition và operator custody.
4. Thiết lập private network, workload identity và audit source.
5. Xây crypto gateway với API allowlist và policy enforcement.
6. Tạo key test, kiểm tra non-exportability và audit.
7. Tích hợp một service canary, kiểm tra encrypt/decrypt/sign.
8. Kiểm thử cross-tenant denial, HSM outage và audit failure.
9. Chuyển dữ liệu/key theo batch có checkpoint.
10. Mở rộng workload theo canary và theo dõi capacity.
11. Diễn tập rotation, backup restore và incident response.
12. Review quyền operator, workload và evidence sau rollout.

Không chuyển toàn bộ workload trước khi xác minh recovery path. Một hệ thống có encrypt/decrypt thành công trong happy path nhưng không restore được key hoặc không truy vết được key version chưa sẵn sàng production.

## 32. Checklist thiết kế HSM boundary

### Boundary và network

- [ ] HSM hardware/security boundary được mô tả theo tài liệu provider.
- [ ] Ứng dụng và PKCS#11 client được xác định là thành phần bên ngoài HSM.
- [ ] Crypto data plane và administrative plane tách biệt.
- [ ] HSM chỉ có private endpoint/route từ workload được phép.
- [ ] TLS/mTLS và certificate validation được bật theo hỗ trợ.
- [ ] Egress và source allowlist được kiểm soát.

### Key và workload

- [ ] KEK/signing private key được tạo/import theo custody policy.
- [ ] Non-extractability và key usage attributes được xác minh.
- [ ] Tenant/purpose/key version được bind server-side.
- [ ] Workload identity riêng, không dùng credential chia sẻ.
- [ ] Crypto gateway có allowlist operation và rate limit.
- [ ] DEK memory exposure được ghi nhận và giảm thiểu.
- [ ] Không có software fallback ngoài policy.

### Operations và evidence

- [ ] Operator, approver, custodian và auditor được phân tách.
- [ ] Quorum/dual control được enforcement ở đúng lớp.
- [ ] HA và backup được thiết kế riêng.
- [ ] Restore drill đã kiểm tra key và metadata mapping.
- [ ] Rotation giữ khả năng đọc dữ liệu lịch sử.
- [ ] Audit có actor, key ID/version, operation và outcome.
- [ ] Audit store độc lập với HSM admin.
- [ ] Có monitoring capacity, policy change và anomaly.
- [ ] Có incident playbook cho app compromise và HSM outage.
- [ ] Có negative test cross-tenant, export, direct admin và fallback.

## 33. Câu hỏi tự kiểm tra

**1. HSM boundary là gì?**

Là ranh giới phần cứng, firmware, key object và operation được bảo vệ theo security model của HSM, cùng các lớp kiểm soát xung quanh nó.

**2. PKCS#11 client có nằm trong HSM hardware boundary không?**

Không. Client library và host application ở bên ngoài, gửi request qua giao diện HSM.

**3. HSM có ngăn ứng dụng bị chiếm quyền gọi Decrypt không?**

Không tự động. HSM có thể giữ key không exportable nhưng vẫn xử lý operation được identity/policy cho phép.

**4. Vì sao cần crypto gateway?**

Để tập trung workload identity, tenant authorization, operation allowlist, key resolution, rate limit và audit trước khi gọi HSM.

**5. KEK và DEK khác nhau thế nào?**

KEK wrap/unwrap DEK; DEK mã hóa dữ liệu thực tế.

**6. Envelope encryption có giữ DEK hoàn toàn trong HSM không?**

Không nhất thiết. Trong mô hình client-side, DEK plaintext có thể đi vào memory của crypto service.

**7. AAD giúp gì cho tenant isolation?**

AAD bind ciphertext với tenant/object/purpose; thay context sẽ làm AEAD authentication fail nếu encoding và validation đúng.

**8. Có nên dùng chung KEK cho mọi tenant không?**

Chỉ khi threat model và yêu cầu isolation cho phép; key riêng giảm blast radius nhưng tăng chi phí quản trị.

**9. Non-extractable có nghĩa ứng dụng không thể lạm dụng key không?**

Không. Ứng dụng vẫn có thể gọi operation mà policy cho phép.

**10. Control plane khác data plane thế nào?**

Control plane quản trị key/policy/lifecycle; data plane thực hiện crypto operation.

**11. Vì sao tách admin network khỏi crypto network?**

Để runtime workload không tiếp cận giao diện quản trị và giảm khả năng leo thang đặc quyền.

**12. Dual control có thể chỉ thực hiện ở web workflow không?**

Không khi HSM yêu cầu quorum riêng; thiết bị phải enforce ceremony theo security model.

**13. HSM cluster có thay thế backup không?**

Không. HA xử lý lỗi node; backup/recovery xử lý mất security domain, site hoặc custody.

**14. Có nên fallback sang software key khi HSM outage không?**

Không âm thầm. Fallback làm thay đổi trust boundary và phải được thiết kế, phê duyệt và audit trước.

**15. Khi rotate KEK, có thể destroy key cũ ngay không?**

Không nếu còn EDK, backup, archive hoặc dữ liệu cần unwrap bằng key cũ.

**16. Vì sao cần giữ immutable key ID/version?**

Để tránh alias đổi đích và bảo đảm ciphertext được giải mã bằng đúng key version.

**17. Java PrivateKey object có đồng nghĩa raw private key được tải vào heap không?**

Không nhất thiết; với PKCS#11 provider, object có thể là handle tới key trong token. Phải xác minh provider behavior.

**18. Vì sao audit cần cả HSM event và gateway event?**

HSM event ghi operation ở provider; gateway event bổ sung tenant, business purpose và authorization context.

**19. Khi app bị compromise nhưng HSM key không exportable, rủi ro còn gì?**

Attacker có thể lạm dụng quyền Sign/Decrypt/Unwrap của workload bị chiếm.

**20. Thiết kế HSM boundary được coi là hoàn chỉnh khi nào?**

Khi hardware, network, identity, key policy, tenant isolation, admin custody, HA/DR, audit, monitoring và negative tests đều được xác minh.

## 34. Tài liệu tham khảo

- NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management.
- NIST SP 800-53 Rev. 5 — Security and Privacy Controls: access control, separation of duties, audit và system integrity.
- FIPS 140-3 — Security Requirements for Cryptographic Modules.
- PKCS #11 Cryptographic Token Interface Base Specification.
- Java Cryptography Architecture (JCA) Reference Guide và SunPKCS11 Provider Documentation.
- NIST SP 800-207 — Zero Trust Architecture.
- Tài liệu HSM security boundary, partition, key attributes, backup/restore, HA và operator roles của vendor đang triển khai.
- Chính sách nội bộ về key inventory, workload identity, change approval, incident response và disaster recovery.

