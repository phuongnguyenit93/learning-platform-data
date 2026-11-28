# Security review của key system

**Security review của key system** là hoạt động đánh giá có hệ thống để xác định liệu kiến trúc, cấu hình, quy trình và bằng chứng vận hành của hệ thống quản lý khóa mật mã có bảo vệ được khóa trong toàn bộ vòng đời hay không. Review cần xem xét cách khóa được tạo, cấp phát, lưu trữ, sử dụng, backup, phục hồi, xoay vòng, thu hồi và hủy; đồng thời kiểm tra danh tính, quyền truy cập, thuật toán, KMS/HSM, ứng dụng tiêu thụ khóa, audit và khả năng khôi phục.

Một key system có thể dùng thuật toán mạnh nhưng vẫn không an toàn nếu private key được export tùy tiện, service account có quyền quá rộng, backup không thể restore, audit log có thể bị xóa hoặc ứng dụng âm thầm chuyển sang software provider khi HSM lỗi. Vì vậy, security review phải đánh giá cả thiết kế lẫn cách hệ thống thực sự vận hành. Kết quả là các phát hiện có bằng chứng, mức độ rủi ro, owner, thời hạn xử lý và cách xác minh remediation.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Chuẩn và assurance**. Nội dung kết nối review với mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, envelope encryption, kiểm soát truy cập, kiểm toán và các tiêu chuẩn quản lý khóa.

## 1. Mục tiêu của security review

Một cuộc review tốt cần trả lời:

- Tổ chức có biết tất cả key, secret và hệ thống nào nằm trong phạm vi không?
- Mỗi key có owner, purpose, classification, consumer và cryptoperiod rõ ràng không?
- Thuật toán, key size, curve, mode và tham số có phù hợp policy không?
- Key material được bảo vệ ở mức nào và có thể export hay không?
- Ai có thể tạo, dùng, quản trị, backup, restore, rotate hoặc destroy key?
- KMS/HSM và ứng dụng có thực thi đúng policy không?
- Có thể phát hiện và điều tra việc sử dụng key bất thường không?
- Có thể khôi phục dữ liệu khi KMS/HSM, region hoặc operator không sẵn sàng không?
- Key bị compromise có thể được revoke/rotate và giới hạn ảnh hưởng không?
- Có bằng chứng chứng minh control hoạt động trong thực tế không?

Mục tiêu không phải chỉ xác nhận có tài liệu policy. Review cần kiểm tra policy có được cấu hình, thực thi, giám sát và kiểm thử hay không.

## 2. Phân biệt security review, audit và certification

Các hoạt động này có liên quan nhưng khác mục tiêu:

| Hoạt động | Trọng tâm | Kết quả thường có |
|---|---|---|
| Security review | Đánh giá thiết kế, cấu hình, threat và hiệu quả kiểm soát | Findings, risk, remediation plan |
| Internal audit | Đánh giá độc lập việc tuân thủ chính sách/quy trình và bằng chứng | Audit observations, nonconformity, action tracking |
| Compliance assessment | Đối chiếu control với tiêu chuẩn hoặc yêu cầu áp dụng | Control status, evidence, gap |
| Penetration test | Thử khai thác đường tấn công trong phạm vi được phép | Exploit path, impact và khuyến nghị |
| Cryptographic module validation | Đánh giá module theo chương trình validation cụ thể | Trạng thái validation của module/configuration |
| Certification/attestation | Xác nhận theo scheme, scope và cơ quan đánh giá cụ thể | Certificate hoặc attestation có phạm vi xác định |

Một HSM dùng cryptographic module đã được FIPS 140-3 validation không có nghĩa toàn bộ key system tự động đạt chuẩn hoặc an toàn. Ứng dụng, IAM, key policy, backup, operator process và cấu hình triển khai vẫn cần được review.

## 3. Xác định phạm vi và ranh giới hệ thống

Trước khi đánh giá, xác định chính xác:

- Business service, dữ liệu và môi trường được bảo vệ.
- KMS, HSM, cloud account/project, region và security domain.
- Software keystore, PKCS#11 provider, Java KeyStore và trust store.
- Certificate authority, PKI, TLS termination và code-signing system.
- Secret manager, identity provider và workload identity.
- Backup, archive, recovery vault, replication và offline media.
- Ứng dụng, batch job, pipeline và service sử dụng key.
- Nhà cung cấp, bên vận hành và external trust boundary.
- Tenant, data residency và yêu cầu pháp lý/hợp đồng liên quan.

Ranh giới cần thể hiện cả luồng key material và luồng quyền. Ví dụ, ứng dụng có thể không nhận private key nhưng vẫn có quyền yêu cầu HSM ký; đó vẫn là một đường sử dụng key cần được đánh giá.

## 4. Lập inventory trước khi review

Không thể đánh giá đầy đủ một hệ thống nếu không biết các key và consumer nằm ở đâu. Inventory nên có:

| Trường | Nội dung cần biết |
|---|---|
| Key ID/version | Định danh ổn định và phiên bản |
| Key type | Symmetric, private, public, DEK, KEK, signing hoặc MAC |
| Algorithm/profile | Thuật toán, key size/curve và tham số liên quan |
| Purpose | Encryption, signing, TLS, backup, wrapping... |
| Owner | Nhóm chịu trách nhiệm |
| Consumer | Ứng dụng, workload, tenant hoặc dữ liệu sử dụng |
| Backend | KMS, HSM, software keystore hoặc OS store |
| Exportability | Non-exportable, wrapped-only hoặc exportable theo policy |
| Lifecycle | Created, active, decrypt-only, disabled, revoked, pending destruction |
| Cryptoperiod | Thời gian sử dụng và mốc rotate/review |
| Backup/recovery | Backup domain, key version dependency và restore procedure |
| Classification | Mức độ nhạy cảm và business criticality |

Đối chiếu inventory với API/resource inventory, ứng dụng thực tế, backup catalog và certificate inventory. Key không có owner, key version không rõ consumer hoặc consumer không có key reference là những dấu hiệu cần điều tra.

## 5. Xây dựng threat model

Threat model giúp review tập trung vào cách key có thể bị lộ, bị sử dụng sai hoặc bị mất khả năng phục hồi. Xác định:

- Tài sản cần bảo vệ: key material, wrapped key, key metadata, policy, audit evidence và dữ liệu phụ thuộc.
- Threat actor: attacker bên ngoài, insider, workload bị chiếm quyền, operator, nhà cung cấp hoặc malware.
- Trust boundary: application-to-KMS, admin-to-HSM, cloud account, region, CI/CD và backup storage.
- Entry point: API, management console, SDK, PKCS#11, file keystore, pipeline và recovery procedure.
- Abuse case: export key, cấp quyền decrypt, sửa policy, giả mạo certificate, xóa backup hoặc tắt audit.
- Impact: confidentiality, integrity, authenticity, availability và recoverability.

~~~mermaid
flowchart TD
    A["Threat actor / compromised workload"] --> B["Identity and network boundary"]
    B --> C["KMS / HSM / keystore"]
    C --> D["Key operations"]
    D --> E["Application data / signatures"]
    F["Admin and policy plane"] --> C
    G["Backup and recovery"] --> C
    H["Audit and monitoring"] --> I["Detection / response"]
    C --> H
    D --> H
    F --> H
    G --> H
~~~

Threat model cần bao gồm cả tình huống availability: KMS outage, mất region, operator nghỉ việc, mất recovery share hoặc key version bị xóa sớm. Một hệ thống có thể chống lộ key nhưng vẫn thất bại nếu không thể giải mã dữ liệu hợp lệ.

## 6. Review kiến trúc và cryptographic boundary

Đánh giá nơi key được tạo, xử lý và lưu trữ:

- Key được tạo bên trong KMS/HSM hay sinh trong ứng dụng rồi import?
- Plaintext key material có bao giờ đi qua process, network, disk hoặc log không?
- HSM có giữ key non-exportable theo đúng use case không?
- KMS thực hiện operation hay chỉ quản lý wrapping key?
- DEK được xử lý trong memory bao lâu và có cache không?
- Software provider có thể trở thành fallback ngoài dự kiến không?
- Các trust boundary có xác thực lẫn nhau và mã hóa kênh không?
- Key handle/reference có bị coi nhầm là key material không?

Vẽ data-flow diagram cho key material và control-flow diagram cho request/authorization. Cần phân biệt plaintext key, wrapped key, public key, certificate, key handle và metadata; mỗi loại có yêu cầu bảo vệ khác nhau.

## 7. Review thuật toán và tham số mật mã

Đối chiếu cấu hình thực tế với security standard và use case:

- Symmetric encryption: thuật toán, key size, mode, nonce/IV và authentication tag.
- Asymmetric encryption: key type, size/curve, padding và parameter profile.
- Digital signature: signature algorithm, digest, PSS/ECDSA parameters và verification policy.
- MAC: thuật toán, key size và cách so sánh tag.
- Key derivation: KDF, salt, context và work factor.
- Randomness: nguồn entropy và SecureRandom/provider được sử dụng.
- Key wrapping: thuật toán, integrity/authentication và context binding.
- Certificate: key usage, extended key usage, subject/SAN, issuer và validity.

Không chỉ kiểm tra tên thuật toán. Ví dụ, AES-GCM cần nonce duy nhất trong phạm vi key và tag được xác thực; RSA-PSS cần tham số nhất quán giữa sign và verify; OAEP cần digest/MGF parameters phù hợp. Một tên transformation chung có thể che giấu khác biệt giữa provider.

Review cũng cần tìm thuật toán legacy, tham số mặc định không được pin, provider order không ổn định hoặc fallback không được phê duyệt.

## 8. Review tạo và cấp phát key

Kiểm tra:

- Key generation dùng CSPRNG/entropy source được phê duyệt.
- Key được tạo đúng backend, key type, size/curve và purpose.
- Import key có nguồn gốc, integrity và dual control phù hợp.
- Key ID, alias, owner và consumer được đăng ký.
- Key attributes như sensitive, extractable và allowed mechanisms đúng policy.
- Quy trình cấp phát không đưa key material vào ticket, chat hoặc repository.
- Mỗi môi trường có key riêng hoặc có ranh giới tách biệt theo policy.
- Key được cấp cho workload bằng identity có scope hẹp.

Không dùng chung một key cho nhiều purpose không tương thích chỉ vì tiện quản lý. Nếu có ngoại lệ, phải có threat analysis, owner và approval rõ.

## 9. Review lưu trữ và bảo vệ key material

Đánh giá các lớp bảo vệ:

- HSM/KMS protection level và trạng thái validation nếu có.
- Software keystore encryption, password/KDF và filesystem permissions.
- Key non-exportability và quyền export/unwrap.
- Tách biệt key material với backup ciphertext và password bảo vệ.
- Memory, heap dump, crash dump, swap và temporary file.
- Key replication, cache và session lifetime.
- Quyền quản trị storage, HSM partition và security domain.
- Bảo vệ physical media và recovery shares.

Không chấp nhận kết luận “key an toàn vì file đã mã hóa” nếu password nằm cạnh file, quyền đọc quá rộng hoặc file tạm chưa được xử lý. Với HSM, review cả cấu hình thiết bị, firmware, partition, operator role và backup domain.

## 10. Review IAM và separation of duties

Key system cần tách các quyền:

| Vai trò | Quyền có thể cần | Quyền cần hạn chế |
|---|---|---|
| Runtime workload | Operation đúng purpose như encrypt/decrypt/sign | Key admin, export, policy update, destroy |
| Key administrator | Tạo key, metadata và policy theo quy trình | Sử dụng key nghiệp vụ nếu không cần |
| Security approver | Phê duyệt thao tác nhạy cảm | Tự thực hiện và tự phê duyệt cùng một change |
| Backup operator | Backup/restore theo scope | Export plaintext hoặc đọc dữ liệu không cần thiết |
| Auditor | Đọc evidence và policy | Thay đổi key, policy hoặc audit log |
| Emergency operator | Quyền tạm thời trong incident | Quyền vĩnh viễn và phạm vi rộng |

Review least privilege, MFA, workload identity, session duration, role assumption, break-glass, dual control và access review. Kiểm tra quyền thực tế từ policy/IAM API thay vì chỉ dựa trên role description.

## 11. Review KMS/HSM và provider

Với KMS, kiểm tra:

- Key policy, IAM policy và grant.
- Region, replication, key version và alias.
- Key state, rotation, deletion window và protection level.
- Encryption context/condition và operation permissions.
- Audit event, quota, throttling và service dependency.

Với HSM, kiểm tra:

- Module/model, firmware và security configuration.
- Partition, role, authentication, quorum và operator ceremony.
- Key attributes, object access và allowed mechanisms.
- Backup/restore domain, replication và tamper response.
- Vendor support, lifecycle và quy trình thay thế thiết bị.

Với Java/JCA provider, kiểm tra:

- Provider name/version và thứ tự provider.
- KeyStore type và backend thực tế.
- Transformation, algorithm parameters và default behavior.
- Key object có phải opaque handle hay exportable object.
- Exception/fallback behavior khi provider unavailable.
- Compatibility matrix khi nâng JDK/provider.

## 12. Review envelope encryption

Đối với envelope encryption, đánh giá toàn bộ quan hệ DEK/KEK:

1. DEK được tạo bằng KMS hoặc CSPRNG theo kiến trúc được duyệt.
2. DEK plaintext chỉ tồn tại trong memory và scope cần thiết.
3. KEK trong KMS/HSM wrap DEK.
4. Ciphertext, wrapped DEK và metadata được lưu nhất quán.
5. Encryption context/AAD ràng buộc đúng tenant, object hoặc purpose.
6. Quyền unwrap chỉ cấp cho workload cần thiết.
7. DEK cache có TTL, scope và revocation behavior rõ.
8. Rotation KEK có quy trình rewrap; rotation DEK có quy trình re-encrypt.

~~~mermaid
flowchart TD
    A["Application identity"] --> B["KMS/HSM: GenerateDataKey"]
    B --> C["Plaintext DEK in memory"]
    B --> D["Wrapped DEK"]
    C --> E["AEAD encrypt data"]
    E --> F["Ciphertext + authenticated metadata"]
    D --> G["Key reference and version"]
    F --> H["Data store"]
    G --> H
    B --> I["KMS audit"]
    E --> J["Application audit"]
~~~

Review phải xác minh ứng dụng không lưu plaintext DEK vào disk/log, không bỏ qua AEAD tag và không cho phép một tenant dùng wrapped DEK của tenant khác.

## 13. Review key lifecycle và cryptoperiod

Kiểm tra quy trình và bằng chứng cho từng trạng thái:

- Creation và activation.
- Distribution/provisioning.
- Active use và usage monitoring.
- Rotation và version migration.
- Deactivation hoặc decrypt-only.
- Revocation và consumer update.
- Backup, recovery và retention.
- Destruction/zeroization.

Cryptoperiod phụ thuộc loại key, purpose, thuật toán, lượng dữ liệu, exposure và tiêu chuẩn áp dụng. Không dùng một con số cố định cho mọi key. Review cần đối chiếu policy nội bộ với hướng dẫn tiêu chuẩn và xác minh job rotation có thực sự hoàn tất.

Key version cũ có thể còn cần để giải mã dữ liệu lịch sử hoặc backup. Không destroy trước khi inventory chứng minh dependency đã được xử lý và recovery test đã đạt.

## 14. Review backup, restore và disaster recovery

Một key system an toàn phải khôi phục được trong điều kiện đã xác định. Kiểm tra:

- Backup key được phép theo policy và backend/vendor procedure.
- Wrapped backup package và wrapping key được tách biệt.
- Backup storage có encryption, access control, immutable retention và account separation.
- Key version cũ còn được giữ khi ciphertext/backup phụ thuộc.
- Recovery shares/quorum được kiểm soát và custodians được kiểm kê.
- Restore runbook có approval, identity tạm thời và audit.
- Restore test có kết quả, thời gian và bằng chứng.
- KMS/HSM outage hoặc regional failure có phương án được diễn tập.
- Temporary plaintext và session được cleanup sau restore.

Chỉ có bản backup không chứng minh khả năng phục hồi. Review cần kiểm tra một lần restore thực tế trong môi trường kiểm soát.

## 15. Review certificate, PKI và trust

Đánh giá:

- CA hierarchy, trust anchor và quyền cấp phát.
- CSR approval, certificate profile và identity binding.
- Key usage/EKU, SAN, issuer và validity.
- Certificate renewal, revocation và CRL/OCSP distribution.
- Private key protection và non-exportability.
- TLS hostname verification và algorithm constraints.
- Certificate inventory, expiry monitoring và consumer migration.
- Code-signing key custody và release approval.

Certificate công khai không cần giữ bí mật như private key, nhưng tính toàn vẹn, issuer trust và binding với identity rất quan trọng. Revoking certificate không tự động destroy private key; cần review cả hai quy trình.

## 16. Review ứng dụng và tích hợp mật mã

Kiểm tra cách ứng dụng sử dụng key:

- Chỉ gọi operation được phép cho đúng purpose.
- Không hardcode password, token hoặc key material.
- Không ghi secret, plaintext DEK hoặc private key vào log.
- Xác thực ciphertext/tag trước khi sử dụng plaintext.
- Pin algorithm/parameters khi cần, không phụ thuộc default ngoài ý muốn.
- Quản lý nonce/IV đúng yêu cầu của mode.
- Không fallback sang provider hoặc key khác ngoài policy.
- Xử lý exception, timeout, throttling và KMS outage đúng cách.
- Không để key object hoặc credential tồn tại lâu hơn cần thiết.
- Có test cho rotation, revoke, provider upgrade và restore.

Review code, configuration, runtime telemetry và test result. Source code đúng không đủ nếu production config khác hoặc runtime có provider khác.

## 17. Review audit, logging và monitoring

Audit cần bao phủ:

- Key generate/import, policy update và permission grant.
- Encrypt/decrypt/sign/verify/wrap/unwrap.
- Export, backup, restore, rotation, revoke và destroy.
- Denied request và lỗi kỹ thuật.
- Break-glass, key ceremony và thay đổi audit configuration.

Mỗi event cần principal, key ID/version, operation, timestamp, outcome, policy decision và request/correlation ID khi có thể. Không ghi key material, password, PIN, token hoặc plaintext nhạy cảm.

Review việc gửi log tới miền lưu trữ tách biệt, immutable/WORM nếu phù hợp, phân quyền emit/read/configure/delete và alert khi audit pipeline bị tắt hoặc mất event. Kiểm tra detection cho export bất thường, decrypt/sign volume tăng đột biến và quyền vừa được mở rộng.

## 18. Review threat response và compromise handling

Một key system cần quy trình khi key hoặc principal bị compromise:

1. Xác định key ID/version, loại key và consumer.
2. Xác định operation đã xảy ra và khoảng thời gian nghi ngờ.
3. Cô lập principal/session và chặn operation không cần thiết.
4. Disable/revoke key theo policy, có đánh giá impact.
5. Tạo key mới và cập nhật consumer.
6. Rewrap DEK hoặc re-encrypt dữ liệu nếu cần.
7. Revoke certificate và phát hành certificate mới nếu private key liên quan.
8. Kiểm tra backup, artifact, cache và bản export.
9. Bảo toàn audit evidence và chain of custody.
10. Xác minh old key không còn được dùng ngoài mục đích cho phép.

Review diễn tập tabletop hoặc incident exercise để kiểm tra owner, quyền quyết định, thứ tự hành động và thời gian phục hồi.

## 19. Review availability và failure handling

Đánh giá KMS/HSM là dependency:

- Timeout, retry bounded, exponential backoff và jitter.
- Circuit breaker, bulkhead và queue giới hạn.
- Phân loại unavailable, throttled, denied, invalid request và key state.
- Fail-closed cho operation không thể xác thực hoặc thực hiện theo policy.
- Graceful degradation cho chức năng không phụ thuộc key.
- DEK cache chỉ khi được policy cho phép, có TTL/scope/revocation handling.
- Multi-region failover giữ đúng key identity và policy.
- Recovery traffic không gây quá tải khi service phục hồi.

Không chấp nhận fallback tự động sang software key, thuật toán yếu hoặc bỏ qua xác thực dữ liệu. Review cần xem test evidence chứ không chỉ runbook trên giấy.

## 20. Bằng chứng cần thu thập

Evidence phải đủ để người review khác có thể lặp lại kết luận. Ví dụ:

| Chủ đề | Evidence phù hợp |
|---|---|
| Inventory | Export metadata đã làm sạch, owner và consumer mapping |
| Architecture | Data-flow, trust boundary, key hierarchy |
| Crypto policy | Standard, algorithm profile, key attribute report |
| KMS/HSM | Key policy, IAM policy, module/configuration evidence |
| Access | Role/grant listing, access review và approval |
| Lifecycle | Rotation job history, key state và destruction record |
| Backup/DR | Backup catalog, restore test report và recovery runbook |
| PKI | CA policy, certificate inventory, revocation evidence |
| Application | Code/config review, provider list và integration test |
| Audit | Sample event đã redacted, retention và SIEM alert |
| Operations | Incident exercise, outage test và remediation record |

Ưu tiên evidence trực tiếp từ hệ thống và có timestamp. Screenshot đơn lẻ có thể thiếu ngữ cảnh; cần kèm resource ID, environment, query/filter và thời điểm lấy dữ liệu. Không thu thập key bytes hoặc secret value làm bằng chứng.

## 21. Phương pháp thực hiện review

Một quy trình có thể triển khai theo các bước:

1. **Scope:** xác định service, dữ liệu, môi trường, provider và tiêu chuẩn áp dụng.
2. **Inventory:** thu thập key, consumer, owner và dependency.
3. **Architecture:** xem data flow, trust boundary và threat model.
4. **Control mapping:** liên kết yêu cầu với control, owner và evidence.
5. **Configuration review:** kiểm tra KMS/HSM, IAM, algorithm, lifecycle và audit.
6. **Operational review:** phỏng vấn owner, xem runbook, rotation, backup và incident.
7. **Technical validation:** chạy test an toàn, read-only checks và fault injection được phê duyệt.
8. **Evidence analysis:** xác minh tính mới, tính toàn vẹn và phạm vi evidence.
9. **Findings:** ghi gap, impact, likelihood, root cause và risk.
10. **Remediation:** thống nhất owner, deadline, kế hoạch và cách kiểm chứng.
11. **Retest:** kiểm tra lại observed state và bằng chứng sau khắc phục.

~~~mermaid
flowchart TD
    A["Scope and criteria"] --> B["Inventory and architecture"]
    B --> C["Threat model and control mapping"]
    C --> D["Configuration and operation review"]
    D --> E["Technical validation"]
    E --> F["Evidence and findings"]
    F --> G["Risk treatment plan"]
    G --> H["Remediation"]
    H --> I["Retest and close"]
~~~

## 22. Ma trận control và evidence

Ma trận giúp tránh review rời rạc:

| Control objective | Câu hỏi đánh giá | Evidence |
|---|---|---|
| Key ownership | Mỗi key có owner và purpose không? | Inventory, owner attestation |
| Strong cryptography | Thuật toán/profile có được phê duyệt không? | Crypto standard, config report |
| Key protection | Key material có được bảo vệ và hạn chế export không? | HSM/KMS attributes, policy |
| Least privilege | Principal có đúng operation/scope không? | IAM/KMS policy, access review |
| Lifecycle | Rotation/revocation/destruction có được thực hiện không? | Job history, key state, records |
| Recovery | Backup có restore được không? | Restore test, DR evidence |
| Auditability | Operation và thay đổi quyền có được ghi không? | Sample event, pipeline health |
| Incident response | Có thể xử lý key compromise không? | Runbook, exercise, incident record |
| Change control | Thay đổi có approval và rollback không? | Change ticket, IaC review |
| Provider assurance | Module/backend có phù hợp yêu cầu không? | Validation certificate, configuration |

Mỗi control nên có trạng thái effective, partially effective, ineffective, not applicable hoặc not verified, cùng lý do và evidence reference. Không đánh dấu effective chỉ vì tài liệu policy tồn tại.

## 23. Tham chiếu tiêu chuẩn và framework

Các tài liệu dưới đây thường hữu ích khi xây dựng review criteria:

| Tài liệu | Phạm vi liên quan | Cách dùng trong review |
|---|---|---|
| NIST SP 800-57 Part 1 Rev. 5 | General guidance về key management | Phân loại key, lifecycle, protection, cryptoperiod và usage |
| NIST SP 800-152 | Framework cho Cryptographic Key Management Systems | Xem xét yêu cầu và thành phần của CKMS |
| NIST SP 800-53 Rev. 5 | Security/privacy controls | Tham chiếu AC, AU, CM, CP, SC và CA controls |
| FIPS 140-3 | Security requirements cho cryptographic modules | Xác minh module validation và cấu hình được đánh giá |
| ISO/IEC 27001:2022 Annex A | Information security controls | Đối chiếu use of cryptography, logging, monitoring, access và backup |
| ISO/IEC 27002:2022 | Hướng dẫn triển khai control | Thiết kế quy trình và biện pháp vận hành |
| PCI DSS v4.0.1 | Bảo vệ account data trong môi trường thuộc phạm vi PCI | Đối chiếu key management requirements khi hệ thống nằm trong PCI scope |
| SOC 2 Trust Services Criteria | Assurance về security, availability, confidentiality và tiêu chí liên quan | Tổ chức evidence và đánh giá control theo scope engagement |

Ví dụ mapping trong NIST SP 800-53 Rev. 5 gồm SC-12 (Cryptographic Key Establishment and Management), SC-13 (Cryptographic Protection), AC-2 (Account Management), AC-3 (Access Enforcement), AC-6 (Least Privilege), AU-2 (Event Logging), AU-9 (Protection of Audit Information), CP-9 (System Backup), CP-10 (System Recovery), CM-6 (Configuration Settings), RA-3 (Risk Assessment) và CA-2 (Control Assessments). Mapping phải được xác minh với control catalog và tailoring áp dụng cho hệ thống. NIST SP 800-152 là profile dành cho Cryptographic Key Management Systems trong bối cảnh liên bang Hoa Kỳ; khi áp dụng ngoài bối cảnh đó, cần chọn profile/control phù hợp thay vì mặc định coi mọi yêu cầu là bắt buộc.

ISO/IEC 27001:2022 có các control liên quan như 8.24 (Use of cryptography), 8.15 (Logging), 8.16 (Monitoring activities), 5.17 (Authentication information), 5.18 (Access rights), 8.9 (Configuration management), 8.13 (Information backup) và 8.25 (Secure development life cycle). Trong PCI DSS v4.0.1, Requirement 3.6 tập trung vào việc bảo vệ cryptographic keys dùng bảo vệ stored account data; Requirement 3.7 yêu cầu quy trình và thủ tục key management bao phủ vòng đời khóa được xác định và triển khai. Chỉ áp dụng mapping PCI khi hệ thống nằm trong scope PCI tương ứng.

Phiên bản tiêu chuẩn, control wording, applicability và yêu cầu đánh giá có thể thay đổi. Trước khi dùng làm tiêu chí audit/compliance, cần xác nhận bản chính thức hiện hành, hợp đồng, regulatory scope và tailoring của tổ chức.

## 24. FIPS validation không chứng minh toàn bộ key system an toàn

FIPS 140-3 đặt yêu cầu cho cryptographic module và chương trình CMVP đánh giá module theo cấu hình/phạm vi được xác định. Khi review:

- Xác minh đúng module, version, firmware/software và operational environment.
- Kiểm tra trạng thái validation và certificate details từ nguồn chính thức.
- Xác minh deployment đang dùng đúng validated configuration.
- Xem security policy của module, approved mode và giới hạn sử dụng.
- Kiểm tra cách ứng dụng kết nối và sử dụng module.
- Đánh giá key policy, IAM, backup, audit và operational procedures bên ngoài module.

Không tuyên bố toàn bộ ứng dụng hoặc key management process FIPS certified chỉ vì dùng một module đã validation. Validation của module là một bằng chứng thành phần; system-level assurance cần review rộng hơn.

## 25. Phân loại findings và đánh giá rủi ro

Một finding nên ghi:

- ID, title và control objective.
- Asset/key ID, environment và owner.
- Expected state và observed state.
- Evidence reference và thời điểm quan sát.
- Threat scenario và root cause.
- Impact lên confidentiality, integrity, availability, authenticity hoặc recoverability.
- Likelihood, exposure và blast radius.
- Existing compensating controls.
- Risk rating và deadline xử lý.

Ví dụ mức độ:

| Mức | Ví dụ | Phản ứng |
|---|---|---|
| Critical | Private key production export plaintext ngoài policy; KEK compromise; không còn đường khôi phục dữ liệu quan trọng | Incident/containment ngay, escalation và risk owner |
| High | Quyền decrypt/export quá rộng; audit bị tắt; key version quá hạn vẫn dùng cho signing | Ưu tiên khắc phục, deadline ngắn và theo dõi chặt |
| Medium | Rotation trễ trong giới hạn bù trừ; restore test quá hạn; certificate sắp hết hạn | Kế hoạch remediation có owner và deadline |
| Low | Metadata/inventory thiếu field nhưng không ảnh hưởng trực tiếp đến operation | Cập nhật theo kế hoạch và cải thiện governance |

Risk rating cần dựa trên impact, likelihood, exposure, key criticality và độ tin cậy evidence. Không hạ mức chỉ vì chưa thấy dấu hiệu khai thác; thiếu log có thể khiến khả năng quan sát thấp.

## 26. Ví dụ finding

**Finding:** Workload production có quyền export KEK không phù hợp với purpose.

| Trường | Nội dung minh họa |
|---|---|
| Asset | production/customer-data-kek |
| Expected | Chỉ encrypt/decrypt qua KMS; export bị deny |
| Observed | Role customer-api-runtime có operation export |
| Evidence | KMS policy snapshot, IAM grant và policy-change event |
| Threat | Workload bị chiếm quyền có thể tạo bản sao key hoặc wrapped export ngoài quy trình |
| Impact | Có thể ảnh hưởng dữ liệu được bảo vệ bởi KEK và backup phụ thuộc |
| Rating | High hoặc Critical tùy khả năng export thực tế và exposure |
| Root cause | Policy dùng role dùng chung cho runtime và administration |
| Remediation | Tách role, thu hồi export grant, kiểm tra lịch sử export, rotate/rewrap nếu cần |
| Retest | Xác minh runtime export bị deny và encrypt/decrypt hợp lệ vẫn hoạt động |

Finding cần giữ bằng chứng đủ để reviewer khác lặp lại kết luận. Không đính kèm key material hoặc wrapped package vào ticket.

## 27. Exception và risk acceptance

Không phải mọi gap đều có thể sửa ngay. Exception cần:

- Finding/control ID liên quan.
- Lý do kỹ thuật hoặc nghiệp vụ.
- Risk owner có thẩm quyền.
- Scope rõ: key, principal, operation, environment và dữ liệu.
- Biện pháp bù trừ.
- Ngày bắt đầu và ngày hết hạn.
- Approval và bằng chứng.
- Kế hoạch khắc phục hoặc quyết định chấp nhận rủi ro.

Không chấp nhận exception vô thời hạn cho quyền export rộng, audit bị tắt hoặc key không thể khôi phục. Khi exception hết hạn, phải kiểm tra lại trạng thái và mở finding nếu gap còn tồn tại.

## 28. Remediation và retest

Remediation cần xử lý nguyên nhân gốc:

1. Xác định policy/config/code/process tạo ra gap.
2. Đánh giá dependency và blast radius.
3. Chuẩn bị change plan, approval, rollback và recovery.
4. Thực hiện thay đổi theo least privilege.
5. Kiểm tra operation hợp lệ vẫn hoạt động.
6. Kiểm tra operation bị cấm thực sự bị deny.
7. Thu thập observed state và audit event mới.
8. Chạy test backup/restore hoặc rotation nếu bị ảnh hưởng.
9. Cập nhật inventory, runbook và control evidence.
10. Retest độc lập và đóng finding khi đủ bằng chứng.

Không đóng finding chỉ vì ticket được đánh dấu resolved. Cần xác minh trạng thái thực tế và kiểm tra side effect như mất khả năng decrypt dữ liệu lịch sử.

## 29. Tần suất và trigger cho security review

Review có thể được thực hiện:

- Trước khi đưa key system hoặc key purpose mới vào production.
- Khi thay KMS/HSM, provider, algorithm hoặc cryptographic module.
- Khi chuyển region, cloud account, tenant hoặc data center.
- Khi thay đổi key policy, exportability hoặc quyền administrator.
- Trước và sau migration, backup architecture hoặc DR redesign.
- Sau incident, unexpected export hoặc phát hiện key compromise.
- Định kỳ theo criticality, regulatory requirement và risk appetite.

Không dùng một lịch cố định cho mọi hệ thống. Key bảo vệ dữ liệu thanh toán hoặc signing root thường cần review sâu và thường xuyên hơn key thử nghiệm đã được cô lập.

## 30. Checklist review hệ thống quản lý khóa

Trước khi kết luận review, hãy xác nhận:

- [ ] Scope, trust boundary, data flow và owner đã được xác định.
- [ ] Inventory bao phủ key, version, consumer, backend và dependency.
- [ ] Threat model xét attacker, insider, workload compromise và outage.
- [ ] Thuật toán, key size/curve, mode và tham số phù hợp policy.
- [ ] Key được tạo/import và cấp phát theo quy trình được duyệt.
- [ ] Key material được bảo vệ; exportability đúng yêu cầu.
- [ ] KMS/HSM/provider và configuration được xác minh.
- [ ] IAM, workload identity, MFA, least privilege và separation of duties phù hợp.
- [ ] Envelope encryption, DEK/KEK, context binding và cache được review.
- [ ] Rotation, revocation, cryptoperiod và destruction có bằng chứng.
- [ ] Backup, restore, recovery quorum và DR đã được test.
- [ ] Certificate/PKI, trust anchor và revocation được kiểm soát.
- [ ] Ứng dụng không log secret và không fallback ngoài policy.
- [ ] Audit bao phủ lifecycle, key operation, policy và admin event.
- [ ] Audit log được bảo vệ, có retention và alert health.
- [ ] Incident response và KMS/HSM outage runbook đã được diễn tập.
- [ ] Standards mapping có phiên bản, scope và evidence phù hợp.
- [ ] Findings có risk, owner, deadline, exception và retest plan.

## 31. Checklist evidence và báo cáo assurance

Mỗi kết luận nên có bằng chứng:

- [ ] Nguồn evidence và thời điểm thu thập được ghi rõ.
- [ ] Resource ID, key ID/version và environment có thể đối chiếu.
- [ ] Evidence đủ mới và đại diện cho phạm vi review.
- [ ] Screenshot/log đã được redaction và không chứa key material.
- [ ] Policy snapshot được đối chiếu với trạng thái thực tế.
- [ ] Test result có expected/actual, setup, outcome và request ID.
- [ ] Exception có approver, owner, scope và expiry.
- [ ] Remediation được xác minh bằng retest.
- [ ] Giới hạn quan sát và điểm chưa xác minh được nêu rõ.
- [ ] Báo cáo phân biệt compliance status với security risk.

Security review của key system là đánh giá kết hợp kiến trúc, mật mã, quyền truy cập, vận hành và bằng chứng. Tiêu chuẩn cung cấp tiêu chí tham chiếu, nhưng assurance chỉ đáng tin khi control được quan sát và kiểm thử trong cấu hình thực tế. Một báo cáo tốt chỉ ra key nào, principal nào, operation nào và bằng chứng nào tạo nên rủi ro; sau đó xác định owner, cách xử lý và phép retest để chứng minh hệ thống đã trở về trạng thái được chấp thuận.
