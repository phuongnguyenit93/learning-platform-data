# Lập key inventory

Trong bài thực hành này, bạn sẽ lập **key inventory** cho một hệ thống Java/SaaS dùng KMS và HSM để bảo vệ dữ liệu, chứng thư và chữ ký số. Kết quả cần cho biết hệ thống đang có những khóa nào, khóa phục vụ mục đích gì, ai chịu trách nhiệm, nằm ở đâu, được workload nào sử dụng, dữ liệu nào phụ thuộc và cần xử lý ra sao khi rotate, revoke hoặc destroy.

Key inventory là danh mục quản lý metadata và quan hệ phụ thuộc của khóa. Đây không phải kho lưu vật liệu khóa. Không đưa raw key, private key, DEK, KEK, password, token hoặc plaintext vào inventory. Một inventory tốt giúp đội bảo mật trả lời nhanh các câu hỏi khi audit, rotation, incident response, recovery và thay đổi kiến trúc.

## 1. Mục tiêu thực hành

Sau khi hoàn thành, bạn có thể:

- Phân biệt key, key version, alias, certificate, secret và key reference.
- Xác định phạm vi các khóa cần đưa vào inventory.
- Thu thập metadata từ KMS/HSM, Java KeyStore, cấu hình ứng dụng và tài liệu vận hành một cách an toàn.
- Thiết kế schema inventory có owner, purpose, algorithm, provider, status, access và dependency.
- Ghi nhận quan hệ giữa KEK, DEK, ciphertext, certificate và workload.
- Phân loại khóa đang hoạt động, không rõ owner, sắp hết cryptoperiod hoặc có nguy cơ bị lộ.
- Đối chiếu inventory với nguồn thực tế để phát hiện khóa mồ côi và dữ liệu thiếu.
- Lập kế hoạch review, rotation, backup, recovery và destruction dựa trên bằng chứng.

**Đầu ra cần có:** một bảng key inventory, một sơ đồ dependency, danh sách phát hiện/rủi ro và kế hoạch khắc phục có owner cùng thời hạn.

## 2. Kịch bản và phạm vi hệ thống

Giả sử bạn đang vận hành nền tảng SaaS quản lý tài liệu cho nhiều tenant. Các service viết bằng Java, dùng envelope encryption:

- Document Service mã hóa nội dung tài liệu bằng AES-GCM.
- Mỗi tài liệu hoặc nhóm dữ liệu có một DEK theo policy.
- DEK được wrap bằng KEK do KMS quản lý.
- Signing Service dùng private key trong HSM để ký tài liệu hoặc audit manifest.
- API Gateway dùng private key/certificate cho TLS.
- Webhook Service dùng HMAC key để xác thực callback.
- Java services dùng workload identity để gọi KMS/HSM.
- Backup và disaster recovery có bản sao dữ liệu mã hóa cùng metadata key version.

Trong bài lab, các ID, tên tenant, thời điểm và trạng thái dưới đây là dữ liệu giả lập. Khi làm trên môi trường thật, dùng resource ID và metadata lấy từ hệ thống được cấp quyền.

Phạm vi inventory gồm:

1. KEK dùng wrap/unwrap DEK.
2. DEK theo từng loại dữ liệu hoặc generation profile.
3. Signing key và public key/certificate liên quan.
4. TLS private key và certificate.
5. HMAC key dùng xác thực webhook hoặc message.
6. Key version, alias, replica và backup reference.
7. Key reference được dùng bởi service, batch job và recovery workflow.

Không cần đưa từng DEK tạm thời vào bảng inventory chính nếu hệ thống sinh DEK theo từng record với số lượng lớn. Thay vào đó, ghi nhận **DEK class/profile**, cách sinh, thuật toán, nơi lưu encrypted DEK, KEK version bảo vệ và metadata truy vết. Nếu một DEK được giữ lâu dài hoặc dùng chung nhiều dữ liệu, hãy inventory nó như một key resource riêng.

## 3. Phân biệt đối tượng cần inventory

| Đối tượng | Ý nghĩa | Cách ghi inventory |
|---|---|---|
| Logical key | Danh tính logic ổn định của một khóa trong hệ thống | Một dòng định danh gốc |
| Key version | Phiên bản vật liệu khóa cụ thể | Một dòng riêng hoặc bảng con theo version |
| Alias | Tên tham chiếu có thể trỏ sang key/version khác | Ghi alias và target hiện tại, không dùng thay version ID |
| Key material | Byte của khóa bí mật hoặc private key | Không lưu trong inventory |
| Key reference | ID/ARN/URI/handle dùng để gọi provider | Có thể lưu nếu phân quyền đọc phù hợp |
| Certificate | Chứng thư chứa public key và thông tin định danh | Ghi fingerprint, subject, issuer, validity |
| Secret | Password, token, credential hoặc dữ liệu bí mật không nhất thiết là key | Quản lý trong secret inventory riêng hoặc liên kết bằng reference |
| DEK profile | Quy tắc sinh DEK và cách bảo vệ encrypted DEK | Ghi pattern, không tạo hàng triệu dòng cho DEK ngắn hạn |

Một certificate không phải private key. Certificate có thể phân phối công khai nhưng private key tương ứng cần được bảo vệ. Tương tự, encrypted DEK không phải raw DEK nhưng vẫn là dữ liệu nhạy cảm vì có thể unwrap nếu KEK còn hoạt động.

## 4. Quy tắc an toàn trước khi discovery

Trước khi thu thập metadata, xác nhận bạn có quyền đọc các hệ thống cần kiểm kê và phạm vi tenant/environment đã được phê duyệt.

- Chỉ đọc metadata và policy cần thiết; không export key material.
- Không gọi API decrypt, sign hoặc export chỉ để xem khóa.
- Không dump heap, process memory hoặc file keystore ra nơi không kiểm soát.
- Không ghi secret value, private key, token hoặc password vào spreadsheet, ticket hay terminal output.
- Không commit file inventory có thông tin nhạy cảm vào Git công khai.
- Hạn chế người được đọc key ID, tenant mapping, provider resource ID và access policy.
- Ghi nguồn, thời điểm và người thu thập để biết metadata đã cũ hay mới.
- Nếu không có quyền truy cập một nguồn, đánh dấu UNKNOWN/NOT_VERIFIED và xin owner xác nhận theo quy trình.

Inventory nên lưu **evidence reference** như đường dẫn tới audit query, resource detail hoặc ticket được kiểm soát quyền; không sao chép toàn bộ tài liệu nhạy cảm vào bảng.

## 5. Các bước discovery

Thực hiện discovery theo nhiều nguồn để tránh bỏ sót khóa chỉ xuất hiện trong một thành phần.

**Bước 1 — Đọc kiến trúc và luồng dữ liệu**

Xác định service nào tạo, dùng, wrap, unwrap, ký, xác minh hoặc phân phối khóa. Theo dõi luồng từ request nghiệp vụ tới KMS/HSM và nơi lưu ciphertext.

**Bước 2 — Kiểm tra KMS/HSM**

Dùng giao diện hoặc API metadata được cấp quyền để liệt kê key resource, version, alias, usage, state, region/partition, policy và rotation setting. Không yêu cầu trả về key bytes.

**Bước 3 — Kiểm tra Java KeyStore và trust store**

Liệt kê alias, entry type, certificate subject/issuer, fingerprint và validity. Không xuất private key hoặc secret entry. Với HSM-backed KeyStore, ghi provider, token/partition reference và key handle theo quy định.

**Bước 4 — Kiểm tra cấu hình ứng dụng**

Tìm key alias, key ID, certificate alias, algorithm, provider name, environment variable name và secret reference trong cấu hình. Chỉ ghi tên biến hoặc reference; không đọc hoặc sao chép giá trị secret.

**Bước 5 — Kiểm tra CI/CD và workload**

Xác định workload identity, service account, pipeline, scheduled job và deployment nào được quyền dùng key. Đối chiếu role/policy với owner của service.

**Bước 6 — Kiểm tra backup và recovery**

Xác định key nào được backup, provider nào giữ bản sao, region nào có replica, ai được restore và dữ liệu nào không thể khôi phục nếu key mất.

**Bước 7 — Đối chiếu audit**

Dùng event tạo, sử dụng, rotation, policy change, disable và destroy để xác định key còn được dùng hay không. Không có event gần đây không đồng nghĩa key không còn dependency; có thể dữ liệu cũ vẫn cần key để restore.

## 6. Schema tối thiểu cho key inventory

Nên nhóm field theo mục đích để bảng dễ review và có thể mở rộng.

| Nhóm | Field | Ý nghĩa |
|---|---|---|
| Identity | inventory_id | ID nội bộ duy nhất trong inventory |
| Identity | logical_key_name | Tên logic có ý nghĩa với nghiệp vụ |
| Identity | provider_resource_id | ID resource thực tế trong KMS/HSM/KeyStore |
| Identity | alias | Alias hiện tại, nếu có |
| Identity | key_version_id | ID bất biến của version |
| Classification | key_type | AES, RSA, EC, Ed25519, HMAC, DEK, KEK... |
| Classification | algorithm_parameters | Key size, curve, mode hoặc profile |
| Classification | purpose | Data encryption, key wrapping, signing, TLS, MAC, key agreement |
| Classification | data_classification | Dữ liệu mà khóa bảo vệ |
| Location | provider | KMS, HSM, JCA provider, KeyStore hoặc platform |
| Location | region_partition | Region, account, project, token hoặc partition |
| Location | exportability | Non-exportable, wrapped export hoặc exportable theo policy |
| Ownership | business_owner | Owner chịu trách nhiệm nghiệp vụ |
| Ownership | technical_custodian | Team hoặc role quản trị kỹ thuật |
| Ownership | service_consumers | Service, workload và batch job sử dụng |
| Access | principals | Principal được phép gọi operation |
| Access | allowed_operations | Encrypt, Decrypt, Sign, Verify, Wrap, Unwrap... |
| Lifecycle | status | Planned, Active, Disabled, PendingDeletion, Destroyed |
| Lifecycle | created_at | Thời điểm tạo |
| Lifecycle | activated_at | Thời điểm bắt đầu sử dụng |
| Lifecycle | cryptoperiod_end | Mốc kết thúc originator usage theo policy |
| Lifecycle | rotation_due_at | Mốc rotation dự kiến |
| Lifecycle | last_used_at | Lần sử dụng gần nhất theo audit |
| Dependency | protected_data_refs | Dataset, table, bucket hoặc record class phụ thuộc |
| Dependency | wrapped_by / wraps | Quan hệ KEK-DEK |
| Dependency | replicas | Replica và region |
| Dependency | backup_refs | Backup/escrow reference và retention |
| Assurance | audit_source | Nguồn audit độc lập |
| Assurance | evidence_ref | Link/reference tới bằng chứng được kiểm soát |
| Assurance | metadata_source | Nguồn đã cung cấp metadata, ví dụ KMS API hoặc KeyStore inventory |
| Assurance | collected_at | Thời điểm thu thập metadata |
| Assurance | last_reviewed_at | Thời điểm review |
| Assurance | risk_level | Critical, High, Medium, Low hoặc Unknown |
| Assurance | findings | Vấn đề và hành động cần xử lý |

Không phải mọi hệ thống đều cung cấp mọi field. Nếu chưa xác minh được, dùng trạng thái rõ ràng như UNKNOWN, NOT_APPLICABLE hoặc NOT_VERIFIED; không để ô trống khiến người review không biết đó là thiếu dữ liệu hay không áp dụng.

## 7. Mẫu bảng inventory có thể điền

Bắt đầu bằng bảng nhỏ dưới đây rồi mở rộng theo schema ở phần trước. Giá trị trong bảng là ví dụ giả lập cho bài lab.

| Inventory ID | Logical key | Version | Type / Purpose | Provider / Location | Owner / Consumer | Status | Exportability | Risk |
|---|---|---|---|---|---|---|---|---|
| KI-001 | docs-tenant-a-kek | v3 | AES-256 / Wrap-DEK | Cloud KMS / region-a | Security Platform / Document Service | Active | Non-exportable | High |
| KI-002 | docs-tenant-b-kek | v2 | AES-256 / Wrap-DEK | Cloud KMS / region-a | Security Platform / Document Service | Active | Non-exportable | High |
| KI-003 | signing-manifest | v5 | RSA-3072 / Sign | HSM / partition-sign | PKI Team / Signing Service | Active | Non-exportable | Critical |
| KI-004 | gateway-tls | v4 | EC P-256 / TLS | HSM-backed KeyStore | Platform / API Gateway | Active | Non-exportable | High |
| KI-005 | webhook-hmac | v2 | HMAC-SHA-256 / MAC | KMS / region-a | Integration Team / Webhook Service | Active | Non-exportable | Medium |
| KI-006 | document-dek-profile | profile-v1 | AES-256 / Data encryption | Generated by KMS, used in Document Service | Data Platform / Document Service | Active profile | DEK returned per policy | High |

Ở KI-006, inventory ghi nhận **profile sinh DEK** thay vì giả định chỉ có một DEK dùng chung. Trong hệ thống thật, mỗi DEK có thể có encrypted representation riêng và metadata liên kết tới KEK version.

## 8. Ví dụ một inventory record đầy đủ

Ví dụ dưới đây minh họa record cho KEK của tenant A. Resource ID và tên là dữ liệu giả lập.

| Field | Giá trị mẫu |
|---|---|
| inventory_id | KI-001 |
| logical_key_name | docs-tenant-a-kek |
| provider_resource_id | kms://region-a/keys/key-7f21 |
| alias | alias/docs/tenant-a/current |
| key_version_id | key-7f21/version-3 |
| key_type | Symmetric |
| algorithm_parameters | AES-256, provider-managed |
| purpose | Wrap/Unwrap DEK |
| data_classification | Confidential customer documents |
| provider | Cloud KMS |
| region_partition | region-a / tenant-a security boundary |
| exportability | Non-exportable |
| business_owner | Document Platform Owner |
| technical_custodian | Security Platform Team |
| service_consumers | Document Service, Recovery Worker |
| allowed_operations | Encrypt, Decrypt |
| status | Active |
| created_at | 2026-01-10T09:00:00Z |
| activated_at | 2026-01-10T10:00:00Z |
| rotation_due_at | Theo cryptoperiod policy |
| last_used_at | Đọc từ KMS audit |
| protected_data_refs | documents.tenant_a |
| wraps | DEK profile document-dek-profile-v1 |
| replicas | Chưa xác minh |
| backup_refs | Provider-managed backup, cần xác nhận retention |
| audit_source | KMS audit trail |
| evidence_ref | security-audit://key-7f21 |
| metadata_source | KMS DescribeKey và version inventory |
| collected_at | 2026-11-28T08:00:00Z |
| last_reviewed_at | 2026-11-28 |
| risk_level | High |
| findings | Xác minh replica và backup restore |

Không điền giá trị như “backup an toàn” hoặc “rotation đúng” nếu chưa có bằng chứng. Ghi rõ điều gì đã xác minh và điều gì còn chờ owner.

## 9. Mô hình dependency giữa KEK, DEK và dữ liệu

Inventory cần thể hiện quan hệ phụ thuộc, không chỉ danh sách key độc lập.

~~~mermaid
flowchart TD
    KMS[KEK version v3 in KMS] --> EDEK[Encrypted DEK metadata]
    EDEK --> DOC[Encrypted document payload]
    DOC --> META[Record metadata: key version, nonce, AAD]
    HSM[Signing private key in HSM] --> SIG[Document signature]
    TLS[TLS private key] --> GATEWAY[API Gateway identity]
    HMAC[Webhook HMAC key] --> CALLBACK[Webhook authenticity]
    BACKUP[Backup and replica] --> EDEK
    BACKUP --> DOC
~~~

Khi KEK v3 bị disable hoặc destroy, các encrypted DEK được wrap bằng version đó có thể không unwrap được. Vì vậy, dependency mapping phải nối key version với encrypted DEK, dữ liệu, backup, replica và recovery worker.

Signing key có dependency khác: public key/certificate có thể cần được giữ để xác minh chữ ký cũ. TLS key phụ thuộc certificate lifecycle và deployment endpoint. HMAC key phụ thuộc các producer/consumer cần xác minh message, có thể cần overlap version khi rotation để tránh mất callback hợp lệ.

## 10. Xác định owner và trách nhiệm

Mỗi key resource cần có owner rõ ràng. Có thể phân vai như sau:

| Vai trò | Trách nhiệm |
|---|---|
| Business owner | Xác định dữ liệu và nghiệp vụ cần bảo vệ, chấp nhận rủi ro |
| Technical custodian | Quản lý cấu hình, provider, policy, rotation và trạng thái |
| Service owner | Xác nhận consumer, dependency và lịch triển khai |
| Security approver | Phê duyệt quyền đặc biệt, rotation khẩn cấp hoặc destruction |
| Backup/recovery owner | Quản lý bản sao, restore và diễn tập phục hồi |
| Auditor | Review evidence, access history và tính đầy đủ inventory |

Một team có thể đảm nhận nhiều vai trò ở hệ thống nhỏ, nhưng các thao tác rủi ro cao cần separation of duties theo policy. Không dùng một mailbox hoặc tên team chung làm owner nếu không có người chịu trách nhiệm cụ thể.

Nếu không xác định được owner, đánh dấu ORPHANED/OWNER_UNKNOWN, xếp ưu tiên điều tra và đặt thời hạn xử lý. Không tự xóa key mồ côi trước khi kiểm tra dữ liệu phụ thuộc.

## 11. Kiểm kê quyền truy cập

Với mỗi key, ghi principal và operation cụ thể thay vì chỉ ghi “service có quyền”.

Ví dụ:

| Principal | Key | Operation | Lý do |
|---|---|---|---|
| document-writer | docs-tenant-a-kek | GenerateDataKey | Tạo DEK mới và encrypted DEK |
| document-reader | docs-tenant-a-kek | Decrypt | Unwrap DEK để đọc tài liệu |
| recovery-worker | docs-tenant-a-kek | Decrypt | Restore theo approval |
| platform-admin | docs-tenant-a-kek | Describe / Rotate | Quản trị metadata và rotation |
| break-glass-role | docs-tenant-a-kek | Decrypt | Chỉ dùng khi incident được phê duyệt |

Tên operation cụ thể phụ thuộc API KMS. Một số dịch vụ dùng GenerateDataKey, Encrypt, Decrypt; một số HSM dùng WrapKey/UnwrapKey hoặc lệnh PKCS#11 tương đương.

Rà soát các quyền sau:

- Principal không còn thuộc service hoặc team.
- Quyền Decrypt rộng hơn phạm vi tenant.
- Principal có quyền Export không cần thiết.
- Role quản trị có thể vừa thay policy vừa xóa audit.
- Credential dài hạn thay vì workload identity ngắn hạn.
- Grant JIT chưa được revoke hoặc không có expiration.
- Quyền test/staging còn tồn tại ở production.

Inventory là ảnh chụp có thời điểm. Cần ghi timestamp và nguồn của access policy để biết dữ liệu có còn mới hay không.

## 12. Đánh giá rủi ro và ưu tiên xử lý

Không nên gán mức rủi ro chỉ theo thuật toán hoặc độ dài khóa. Đánh giá cần xét cả dữ liệu, quyền, khả năng export, dependency và trạng thái vận hành.

Các yếu tố gợi ý:

| Yếu tố | Rủi ro tăng khi |
|---|---|
| Data criticality | Khóa bảo vệ dữ liệu nhạy cảm hoặc có ảnh hưởng diện rộng |
| Privilege | Nhiều principal có quyền Decrypt, Export hoặc Destroy |
| Exportability | Raw key có thể rời khỏi KMS/HSM |
| Tenant scope | Một key dùng chung nhiều tenant không có cách ly phù hợp |
| Lifecycle | Không có cryptoperiod, rotation hoặc owner |
| Dependency | Backup/replica không rõ hoặc dữ liệu phụ thuộc chưa kiểm kê |
| Audit | Không có log độc lập hoặc không nối được actor với operation |
| Provider posture | Provider cũ, cấu hình yếu hoặc trạng thái không xác minh |
| Exposure | Key/secret từng nằm trong source, image, log hoặc ticket |

Có thể dùng bốn mức:

- **Critical:** nghi ngờ compromise, key export ngoài kiểm soát, signing key trọng yếu bị lộ hoặc quyền cross-tenant có thể bị lạm dụng.
- **High:** key bảo vệ dữ liệu nhạy cảm nhưng thiếu owner, audit, rotation hoặc dependency map.
- **Medium:** metadata thiếu một phần, policy chưa được review hoặc backup chưa được diễn tập.
- **Low:** inventory đầy đủ, owner và control đã xác minh, chỉ còn cải thiện nhỏ.

Mức rủi ro cần đi kèm lý do, evidence và hành động. Không dùng điểm số giả chính xác nếu chưa có mô hình đánh giá đã được tổ chức phê duyệt.

## 13. Đối chiếu và tìm key mồ côi

Sau khi lập bảng, đối chiếu inventory với nguồn thực tế:

1. Danh sách key resource trong KMS/HSM.
2. Alias và key version.
3. Java KeyStore/trust store.
4. IAM/key policy/grant.
5. Application config và workload deployment.
6. Audit event sử dụng key.
7. Backup/replica và recovery catalog.
8. Certificate inventory và TLS endpoint.

Phân loại chênh lệch:

| Phát hiện | Ý nghĩa | Hành động |
|---|---|---|
| Resource tồn tại nhưng không có inventory row | Có thể là key mồ côi | Xác định owner và dependency |
| Inventory có key nhưng provider không tìm thấy | Metadata cũ hoặc resource đã xóa | Kiểm tra audit và tombstone |
| Key không có owner | Không ai chịu trách nhiệm | Escalate owner discovery |
| Key không có last-used evidence | Chưa đủ bằng chứng không dùng | Kiểm tra archive, backup và batch job |
| Alias trỏ version khác inventory | Inventory stale | Cập nhật target và xác minh consumer |
| Principal không còn tồn tại | Access policy stale | Revoke theo change process |
| Backup không có key reference | Có nguy cơ không restore được | Tạo dependency mapping và restore test |

Không tự động destroy key chỉ vì không thấy lần sử dụng gần đây. Có thể key chỉ phục vụ restore dữ liệu lưu trữ dài hạn hoặc xác minh chữ ký lịch sử.

## 14. Java: biểu diễn metadata inventory an toàn

Có thể dùng Java record để biểu diễn metadata key inventory. Ví dụ chỉ chứa reference và thuộc tính quản lý, không chứa byte của khóa.

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.Set;

public record KeyInventoryEntry(
        String inventoryId,
        String logicalKeyName,
        String providerResourceId,
        String keyVersionId,
        String algorithm,
        String purpose,
        String provider,
        String owner,
        String status,
        boolean exportable,
        Instant createdAt,
        Instant rotationDueAt,
        Set<String> principals,
        Set<String> dependencyRefs) {

    public KeyInventoryEntry {
        requireText(inventoryId, "inventoryId");
        requireText(logicalKeyName, "logicalKeyName");
        requireText(providerResourceId, "providerResourceId");
        requireText(keyVersionId, "keyVersionId");
        requireText(algorithm, "algorithm");
        requireText(purpose, "purpose");
        requireText(provider, "provider");
        requireText(owner, "owner");
        requireText(status, "status");

        if (createdAt == null) {
            throw new IllegalArgumentException("createdAt is required");
        }
        if (rotationDueAt != null && rotationDueAt.isBefore(createdAt)) {
            throw new IllegalArgumentException(
                "rotationDueAt cannot precede createdAt"
            );
        }

        principals = Set.copyOf(Objects.requireNonNull(principals, "principals"));
        dependencyRefs = Set.copyOf(
            Objects.requireNonNull(dependencyRefs, "dependencyRefs")
        );
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
    }
}
~~~

Khi triển khai thật, nên dùng enum cho status, purpose và provider đã chuẩn hóa; bổ sung schema version, region, tenant scope, allowed operations, last-used timestamp và evidence reference. Cần validate thêm key version thuộc logical key, owner còn hiệu lực và provider resource ID đúng format của backend.

Không thêm trường như keyBytes, privateKeyPem, secretValue hoặc password vào record. Inventory nên lưu key reference để service có thể gọi KMS/HSM theo quyền, không lưu vật liệu khóa.

## 15. Bài tập thực hành theo từng bước

Thực hiện theo thứ tự và lưu kết quả trong tài liệu/bảng inventory được tổ chức phê duyệt.

**Bước 1 — Vẽ phạm vi**

Liệt kê service, environment, tenant và luồng dữ liệu cần kiểm kê. Đánh dấu các ranh giới KMS, HSM, KeyStore, secret manager, database và backup.

**Bước 2 — Lập danh sách key class**

Tối thiểu xác định KEK, DEK profile, signing key, TLS key và HMAC key. Với mỗi class, nêu purpose, thuật toán dự kiến và dữ liệu được bảo vệ.

**Bước 3 — Thu thập resource metadata**

Lấy key ID, version, alias, provider, location, status, usage và exportability từ nguồn có thẩm quyền. Ghi source và collected_at.

**Bước 4 — Xác định owner và consumer**

Gắn business owner, technical custodian, service owner, workload identity và các operation được phép.

**Bước 5 — Lập dependency map**

Nối key version với encrypted DEK, ciphertext, certificate, backup, replica, batch job và recovery process.

**Bước 6 — Đối chiếu access policy**

So sánh principal thực tế với owner/consumer đã khai báo. Đánh dấu quyền thừa, quyền cross-tenant và principal không còn tồn tại.

**Bước 7 — Đánh giá lifecycle**

Ghi created_at, activated_at, cryptoperiod, rotation_due_at, last_used_at, trạng thái và kế hoạch retire/destroy. Nếu không biết, ghi UNKNOWN và giao người xác minh.

**Bước 8 — Đánh giá backup/recovery**

Xác định backup reference, retention, quyền restore và lần diễn tập gần nhất. Không đánh dấu recoverable nếu chưa có bằng chứng restore.

**Bước 9 — Phân loại rủi ro**

Gán Critical/High/Medium/Low với lý do và evidence. Mỗi finding cần có owner, hành động, deadline và trạng thái.

**Bước 10 — Review và phê duyệt**

Để business owner, technical custodian và security reviewer xác nhận inventory. Ghi phiên bản, thời điểm review và các ngoại lệ được chấp nhận.

## 16. Mẫu finding và kế hoạch khắc phục

Ví dụ phát hiện từ một lần kiểm kê giả lập:

| Finding ID | Phát hiện | Mức | Hành động | Owner |
|---|---|---|---|---|
| KF-001 | KEK tenant A chưa xác minh replica | High | Đối chiếu KMS replica và thử restore | Security Platform |
| KF-002 | Signing key không có review access gần đây | High | Review principal, approval và HSM audit | PKI Team |
| KF-003 | TLS certificate còn hạn ngắn | Medium | Lập lịch renew và kiểm tra key reuse policy | API Platform |
| KF-004 | HMAC key có consumer cũ chưa xác định | Medium | Đối chiếu webhook client và thu hồi consumer không còn dùng | Integration Team |
| KF-005 | DEK profile chưa ghi rõ key version metadata | High | Bổ sung version ID vào encrypted envelope | Data Platform |
| KF-006 | Một key không có business owner | High | Tìm owner, xác minh dependency trước mọi thay đổi | Service Management |

Không xử lý finding chỉ bằng cách sửa ô inventory. Nếu quyền thực tế đang quá rộng, cần change request để sửa policy. Nếu alias sai, cần xác minh consumer trước khi đổi. Nếu owner không rõ, không tự disable hoặc destroy khóa.

## 17. Kiểm soát chất lượng inventory

Trước khi kết luận inventory hoàn tất, kiểm tra:

- Mỗi key resource có inventory ID và provider resource ID duy nhất.
- Mỗi version có key version ID riêng; alias được ghi như reference có thể thay đổi.
- Mỗi key có purpose, algorithm, provider, status và owner.
- Principal và allowed operation có nguồn xác minh.
- Dependency của ciphertext, encrypted DEK, certificate, backup và replica được ghi nhận.
- Lifecycle có created, active, rotation và retirement/destruction state.
- Các trường chưa xác minh được gắn UNKNOWN/NOT_VERIFIED.
- Mỗi finding có mức rủi ro, evidence, owner và deadline.
- Không có key material, secret hoặc plaintext trong inventory.
- Có collected_at, last_reviewed_at và nguồn dữ liệu cho từng nhóm metadata.

Có thể theo dõi các chỉ số chất lượng:

| Chỉ số | Cách tính |
|---|---|
| Owner coverage | Số key có owner / tổng key trong phạm vi |
| Purpose coverage | Số key có purpose rõ / tổng key |
| Version coverage | Số key có version ID được xác minh / tổng key version |
| Dependency coverage | Số key có dependency map / tổng key cần bảo vệ dữ liệu |
| Access review coverage | Số key có policy/principal được review / tổng key |
| Backup evidence coverage | Số key cần backup có bằng chứng restore / số key cần backup |
| Unknown ratio | Số field trọng yếu còn UNKNOWN / tổng field trọng yếu |

Không đặt mục tiêu 100% bằng cách điền giá trị phỏng đoán. UNKNOWN là tín hiệu quản trị hữu ích nếu có owner và hạn xử lý.

## 18. Duy trì inventory theo vòng đời

Inventory không phải bảng lập một lần rồi bỏ quên. Cần cập nhật khi:

- Tạo hoặc import key mới.
- Sinh key version mới hoặc thay alias.
- Thay đổi owner, service consumer hoặc workload identity.
- Thay đổi key policy, grant hoặc operation.
- Rotate, disable, revoke, schedule deletion hoặc destroy.
- Tạo replica, backup, restore hoặc chuyển region.
- Thay đổi thuật toán, provider hoặc cryptoperiod.
- Phát hiện compromise hoặc sự cố audit.

Có thể tự động đồng bộ metadata KMS/HSM theo lịch và đối chiếu với CMDB/service catalog. Tuy nhiên, owner, purpose, data classification và dependency nghiệp vụ thường cần xác nhận từ team sở hữu ứng dụng. Tự động hóa không loại bỏ trách nhiệm review.

Mỗi lần thay đổi nên có change ID, actor, timestamp, evidence reference và trạng thái phê duyệt. Bản inventory trước đó cần có version history để điều tra sự thay đổi theo thời gian.

## 19. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Lưu raw key trong inventory | Tạo thêm bản sao bí mật và tăng nguy cơ lộ | Chỉ lưu key ID/reference và metadata |
| Chỉ inventory alias | Alias có thể đổi target, không xác định version đã dùng | Lưu provider resource ID và version ID |
| Bỏ qua DEK profile | Không biết dữ liệu phụ thuộc vào KEK nào | Inventory generation profile và envelope metadata |
| Không ghi owner | Không ai chịu trách nhiệm rotation hoặc incident | Bắt buộc business owner và technical custodian |
| Coi không có last-used là không dùng | Có thể phá khả năng restore dữ liệu cũ | Kiểm tra archive, backup và consumer offline |
| Chỉ đọc cấu hình ứng dụng | Bỏ sót key trong KMS/HSM hoặc backup | Đối chiếu nhiều nguồn độc lập |
| Không kiểm tra principal | Quyền thừa và cross-tenant có thể tồn tại | Inventory access policy và review định kỳ |
| Coi backup tồn tại là recovery được | Backup có thể không giải mã hoặc không restore được | Yêu cầu bằng chứng restore |
| Tự xóa key mồ côi | Có thể làm mất dữ liệu không thể phục hồi | Xác minh owner/dependency trước khi disable/destroy |
| Không ghi nguồn và thời điểm | Không biết metadata còn mới hay không | Ghi source, collected_at và last_reviewed_at |

## 20. Tiêu chí hoàn thành bài thực hành

Bài thực hành được xem là hoàn thành khi bạn có thể trình bày và bảo vệ các đầu ra sau:

1. Phạm vi hệ thống, environment, tenant và service đã kiểm kê.
2. Danh mục logical key và từng key version trong phạm vi.
3. Metadata algorithm, purpose, provider, location, status và exportability.
4. Business owner, technical custodian, workload consumer và allowed operations.
5. Dependency map nối KEK, DEK profile, ciphertext, certificate, backup và replica.
6. Access review xác định principal hợp lệ và quyền cần xử lý.
7. Lifecycle review có cryptoperiod, rotation, revoke và destruction state.
8. Risk register có evidence, owner, deadline và remediation.
9. Danh sách field UNKNOWN/NOT_VERIFIED cùng kế hoạch xác minh.
10. Xác nhận inventory không chứa raw key, secret, token hoặc plaintext.

Khi review, người trình bày cần chọn một key quan trọng và lần theo toàn bộ đường đi: key được tạo ở đâu, ai dùng, bảo vệ dữ liệu nào, DEK được wrap bởi version nào, backup nằm ở đâu, audit lấy từ nguồn nào và nếu phải rotate/destroy thì consumer cùng dữ liệu phụ thuộc sẽ được xử lý ra sao.

Key inventory có giá trị khi phản ánh được cả tài nguyên kỹ thuật lẫn quan hệ nghiệp vụ. Một danh sách chỉ có tên khóa và thuật toán không đủ để vận hành an toàn. Khi owner, access, version, dependency, backup, lifecycle và evidence được quản lý cùng nhau, tổ chức có thể kiểm soát rotation, điều tra compromise, phục hồi dữ liệu và hủy khóa có trách nhiệm.
