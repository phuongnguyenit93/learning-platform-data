# Key management audit

**Key management audit** là hoạt động ghi nhận, bảo vệ, rà soát và phân tích các sự kiện xảy ra trong toàn bộ vòng đời khóa mật mã. Audit cần cho biết khóa nào được tạo, ai hoặc workload nào quản lý, khóa được cấp cho mục đích gì, operation nào đã sử dụng khóa, policy nào cho phép thao tác, phiên bản nào đang hoạt động và khóa được rotate, revoke hay destroy vào lúc nào.

Khóa mật mã thường bảo vệ dữ liệu, xác thực workload, ký giao dịch, bảo vệ backup hoặc thiết lập kết nối TLS. Vì vậy, audit không chỉ phục vụ điều tra sau sự cố. Nó còn giúp chứng minh quyền truy cập được kiểm soát, xác nhận quy trình vận hành tuân thủ policy, phát hiện khóa bị sử dụng ngoài mục đích và bảo đảm tổ chức vẫn có thể khôi phục dữ liệu trong thời hạn cần thiết.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Audit và monitoring**. Nội dung kết nối audit với vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, backup, restore, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Vì sao phải audit vòng đời khóa?

Một khóa có thể tồn tại nhiều năm, được dùng bởi nhiều workload và bảo vệ lượng dữ liệu lớn. Nếu chỉ ghi log lúc ứng dụng khởi động, tổ chức sẽ không biết ai đã tạo khóa, ai thay đổi policy, operation nào đã sử dụng khóa hoặc khóa cũ đã được hủy thật sự hay chưa.

Key management audit giúp trả lời:

- Ai hoặc workload nào đã tạo, import, export, sử dụng hoặc xóa khóa?
- Khóa được tạo trong KMS, HSM, software keystore hay một hệ thống khác?
- Thuật toán, key size, purpose và policy nào đã được gán?
- Key ID và version nào đã thực hiện encrypt, decrypt, sign, verify, wrap hoặc unwrap?
- Lần truy cập có được allow hay deny? Quyết định dựa trên policy nào?
- Có ai thay đổi quyền, rotation schedule, key state hoặc audit configuration không?
- Backup nào phụ thuộc vào key version nào?
- Khóa đã bị disable, revoke hoặc destroy chưa; thao tác có đang chờ xóa không?
- Có dấu hiệu key bị sử dụng bất thường hoặc ngoài cryptoperiod không?

Không có audit trail đáng tin cậy, tổ chức khó xác định phạm vi compromise, khó chứng minh separation of duties và có thể xóa nhầm khóa vẫn cần để giải mã dữ liệu lịch sử.

## 2. Phạm vi của key management audit

Audit nên bao phủ mọi nơi tạo, lưu trữ hoặc thực hiện operation bằng khóa:

- KMS cloud hoặc KMS nội bộ.
- HSM, smart card, cryptographic token và PKCS#11 provider.
- Java KeyStore, PKCS#12, JKS và OS-backed keystore.
- Certificate authority, PKI, certificate lifecycle và trust store.
- Ứng dụng dùng software provider để ký, mã hóa hoặc tạo MAC.
- Hệ thống envelope encryption và data key cache.
- Backup platform, recovery vault và key escrow.
- CI/CD signing, code-signing key và release pipeline.
- TLS termination, service mesh và workload identity.
- Secret manager có lưu password bảo vệ key hoặc credential truy cập KMS/HSM.

Mỗi hệ thống có khả năng audit khác nhau. Một HSM có thể ghi nhận session và thao tác object; một KMS có thể ghi request, key ID, principal và encryption context; một file keystore có thể không tự phát audit event khi ứng dụng đọc entry. Khi nguồn không cung cấp event, cần bổ sung telemetry ở lớp ứng dụng hoặc vận hành và ghi rõ giới hạn quan sát.

## 3. Phân biệt control plane và data plane

Key management có hai nhóm hoạt động cần được audit:

- **Control plane:** tạo/import key, gán policy, thay đổi metadata, enable/disable, lên lịch rotation, cấp quyền, revoke và destroy.
- **Data plane:** encrypt, decrypt, sign, verify, generate data key, wrap, unwrap hoặc các operation mật mã khác.

Một kẻ tấn công có thể sửa policy để cấp quyền cho mình trước, rồi mới decrypt dữ liệu. Nếu chỉ audit decrypt, tổ chức có thể bỏ sót thay đổi quyền đã mở đường cho hành động đó.

~~~mermaid
flowchart TD
    A["Principal / workload"] --> B["IAM authentication"]
    B --> C["KMS / HSM policy"]
    C --> D{"Authorization"}
    D -- "Allow" --> E["Key operation"]
    D -- "Deny" --> F["Denied event"]
    E --> G["Data-plane audit"]
    F --> G
    H["Create / policy / rotate / disable / destroy"] --> I["Control-plane audit"]
    G --> J["Central audit pipeline"]
    I --> J
    J --> K["Immutable store / SIEM"]
    K --> L["Detection / investigation / compliance"]
~~~

Control-plane event cho biết cấu hình và trạng thái khóa thay đổi ra sao; data-plane event cho biết khóa đã thực hiện operation nào. Điều tra tốt cần kết nối cả hai nhóm theo principal, key ID, thời gian và request ID.

## 4. Các giai đoạn vòng đời cần ghi nhận

| Giai đoạn | Sự kiện cần audit | Thông tin trọng tâm |
|---|---|---|
| Tạo | Generate, import hoặc provision | Actor, key ID, thuật toán, key size, purpose, backend |
| Cấp phát | Gán owner, alias, consumer hoặc policy | Principal, scope, environment, approval |
| Lưu trữ | Đặt policy, protection level, backup domain | KMS/HSM, key state, exportability, replication |
| Sử dụng | Encrypt, decrypt, sign, verify, wrap, unwrap | Principal, operation, key version, outcome |
| Backup | Export/wrap/backup package | Backup ID, key version, approver, destination |
| Restore | Restore/import/unwrap | Nguồn backup, target, approval, kết quả |
| Xoay vòng | Tạo version mới, chuyển consumer | Version cũ/mới, thời điểm, trạng thái migration |
| Thu hồi | Disable, revoke, deny operation | Lý do, actor, tác động và dependency |
| Hủy | Schedule deletion, destroy hoặc zeroize | Approval, thời hạn chờ, bằng chứng hoàn tất |

Không phải backend nào cũng phát event riêng cho mọi bước. Nếu quy trình gồm nhiều hệ thống, cần có correlation ID hoặc workflow ID để nối event từ KMS/HSM, PKI, ứng dụng và hệ thống backup.

## 5. Phân loại key event

Một event taxonomy thống nhất giúp chuẩn hóa log từ nhiều provider:

| Nhóm | Event tiêu biểu |
|---|---|
| Key creation | key.generate, key.import, key.provision |
| Key metadata | key.label.update, key.tag.update, key.owner.change |
| Access control | key.policy.update, key.grant, key.revoke, key.role.change |
| Key use | key.encrypt, key.decrypt, key.sign, key.verify, key.mac |
| Key wrapping | key.wrap, key.unwrap, data-key.generate |
| Key lifecycle | key.enable, key.disable, key.rotate, key.revoke |
| Backup and recovery | key.backup, key.restore, key.clone, key.recover |
| Certificate | certificate.issue, certificate.renew, certificate.revoke |
| Destruction | key.delete.schedule, key.destroy, key.zeroize |
| Audit administration | audit.configure, audit.disable, audit.destination.change |

Ghi cả event thành công, bị từ chối và thất bại kỹ thuật. Một loạt request bị deny có thể cho thấy credential bị cấu hình sai hoặc có hành vi dò tìm; một operation thất bại do HSM timeout lại cần được phân biệt với quyết định từ chối của policy.

## 6. Thiết kế audit event schema

Audit event nên có schema ổn định để truy vấn, tương quan và lưu trữ lâu dài. Các field quan trọng:

| Field | Ý nghĩa |
|---|---|
| eventId | ID duy nhất của event nguồn |
| eventTime | Thời điểm phát sinh theo UTC |
| ingestTime | Thời điểm collector nhận event |
| eventType | Loại thao tác như key.decrypt hoặc key.policy.update |
| outcome | success, denied hoặc failure |
| principalId | ID ổn định của user, service account hoặc workload |
| principalType | Human, workload, service, administrator hoặc emergency |
| authContext | Identity provider, role, session và assurance context |
| keyId | Định danh khóa ổn định |
| keyVersion | Phiên bản khóa được dùng hoặc thay đổi |
| keyPurpose | Encrypt, sign, TLS, backup hoặc purpose khác |
| algorithm | Thuật toán và profile liên quan |
| operation | Encrypt, decrypt, sign, unwrap, rotate, destroy... |
| provider/backend | KMS, HSM, provider hoặc service thực thi |
| policyDecision | Rule/policy version quyết định allow/deny |
| source | Workload, cluster, namespace, host hoặc application |
| requestId | ID nối với request/trace/workflow |
| approvalRef | Ticket hoặc approval cho thao tác nhạy cảm |
| reasonCode | Lý do hoặc mã lỗi đã chuẩn hóa |

Không phải event nào cũng có đủ mọi field. Tuy vậy, event sử dụng hoặc thay đổi khóa cần xác định được principal, resource, operation, thời gian và outcome. Nếu backend không cung cấp một field, cần ghi nhận nguồn thay thế hoặc giới hạn đó.

## 7. Ví dụ event sử dụng khóa

Ví dụ JSON mô tả một workload thực hiện decrypt bằng một key version cụ thể:

~~~json
{
  "eventId": "evt-01J8KMS92A",
  "eventTime": "2026-11-28T04:12:18.210Z",
  "eventType": "key.decrypt",
  "outcome": "success",
  "principal": {
    "id": "spiffe://prod.example/ns/orders/sa/orders-api",
    "type": "workload",
    "role": "orders-data-decryptor"
  },
  "key": {
    "id": "kms://production/orders-data-kek",
    "version": "v4",
    "purpose": "envelope-encryption",
    "algorithm": "AES-256"
  },
  "operation": "decrypt",
  "backend": "approved-kms",
  "policy": {
    "decision": "allow",
    "policyId": "orders-decrypt-policy",
    "policyVersion": "9"
  },
  "source": {
    "cluster": "prod-cluster-a",
    "namespace": "orders",
    "workload": "orders-api"
  },
  "requestId": "req-4f82a1"
}
~~~

Các ID trong ví dụ là dữ liệu minh họa. Event không chứa ciphertext, plaintext, DEK dạng rõ hoặc key bytes. Tùy backend, event có thể ghi thêm encryption context, region, HSM slot hoặc session ID; chỉ ghi metadata thực sự cần thiết và không làm lộ dữ liệu nhạy cảm.

## 8. Audit tạo và import key

Khi tạo hoặc import key, cần ghi:

- Actor hoặc workload thực hiện.
- Key ID được backend cấp.
- Thuật toán, key size, curve hoặc key type.
- Purpose/use policy: encrypt, decrypt, sign, verify, MAC hoặc key wrapping.
- Nguồn tạo: KMS, HSM, software provider hay import.
- Exportability và protection level nếu backend cung cấp.
- Owner, environment, tenant và application consumer.
- Approval/ticket và kết quả thao tác.

Với key import, cần ghi nguồn gốc và quy trình kiểm soát vật liệu nhập. Không ghi key material, import plaintext package hoặc wrapping secret vào audit. Nếu dùng key ceremony hoặc dual control, event cần liên kết người tham gia và approval evidence mà không tiết lộ bí mật.

## 9. Audit phân quyền và policy

Thay đổi policy có thể làm tăng phạm vi sử dụng khóa. Event cần cho biết:

- Ai tạo, sửa hoặc xóa policy.
- Principal/role nào được cấp hoặc thu hồi quyền.
- Key ID hoặc phạm vi key nào bị ảnh hưởng.
- Operation được cấp: decrypt, sign, export, rotate, delete hoặc administer.
- Điều kiện policy như tenant, encryption context, source network hoặc workload identity.
- Policy version trước và sau thay đổi.
- Approval, lý do và thời điểm có hiệu lực.

Đối với thao tác nhạy cảm như export key, thay đổi trust boundary hoặc cấp quyền decrypt diện rộng, nên áp dụng approval hoặc dual control. Người sửa policy không nên mặc nhiên là người duy nhất phê duyệt và tự cấp quyền.

## 10. Audit operation mật mã

Data-plane audit cần ghi operation nào đã xảy ra, trên key nào và do principal nào yêu cầu. Những operation thường gặp:

| Operation | Ý nghĩa audit |
|---|---|
| Encrypt | Khóa được dùng để mã hóa dữ liệu |
| Decrypt | Khóa được dùng để giải mã |
| Sign | Khóa ký tạo chữ ký |
| Verify | Operation xác minh chữ ký, nếu backend cung cấp |
| MAC | Tạo hoặc kiểm tra message authentication code |
| Wrap/unwrap | Bọc hoặc mở bọc một khóa khác |
| GenerateDataKey | Tạo DEK trong mô hình envelope encryption |
| DeriveKey | Sinh khóa dẫn xuất theo context |
| Export | Đưa key material ra khỏi backend, nếu được phép |

Không phải backend nào cũng ghi được từng operation ở cấp ứng dụng. Ví dụ, một software provider có thể thực hiện Cipher trong tiến trình mà không gửi event đến KMS. Khi cần audit chi tiết, ứng dụng phải phát event metadata đã được kiểm soát hoặc dùng backend cung cấp audit đáng tin cậy.

Không ghi plaintext hoặc key material để chứng minh operation đã xảy ra. Dùng key ID, operation, request ID, outcome và evidence từ backend.

## 11. Audit envelope encryption và data key

Trong envelope encryption, DEK mã hóa dữ liệu; KEK trong KMS/HSM bọc DEK. Audit cần liên kết được hai lớp:

1. Workload yêu cầu KMS tạo DEK hoặc unwrap một DEK đã được bọc.
2. KMS ghi operation trên KEK và key version.
3. Ứng dụng dùng DEK trong phạm vi được phép để mã hóa/giải mã dữ liệu.
4. Ứng dụng lưu ciphertext, wrapped DEK và metadata cần thiết.
5. Audit liên kết backup/data object với key ID/version và request ID.

~~~mermaid
flowchart TD
    A["Workload identity"] --> B["KMS: GenerateDataKey"]
    B --> C["Plaintext DEK trả về tạm thời"]
    B --> D["Wrapped DEK + KEK ID/version"]
    C --> E["Ứng dụng mã hóa dữ liệu"]
    E --> F["Ciphertext"]
    D --> G["Object metadata"]
    F --> H["Encrypted object / backup"]
    G --> H
    B --> I["KMS audit event"]
    E --> J["Application operation event"]
    I --> K["Correlated audit trail"]
    J --> K
~~~

Audit nên ghi KEK ID/version, operation, principal và context phù hợp. Không ghi plaintext DEK. Nếu DEK được cache, cần có policy và telemetry phù hợp để biết operation nào diễn ra tại ứng dụng mà không gọi KMS mỗi lần.

## 12. Audit sử dụng khóa trong HSM

HSM có thể cung cấp audit về:

- Login/logout, token session và role.
- Slot, partition hoặc security domain.
- Tạo, import, wrap, unwrap, sign, decrypt và delete object.
- Thay đổi policy, PIN retry, role hoặc cấu hình thiết bị.
- Backup/restore, quorum và key ceremony.
- Lỗi thiết bị, tamper event hoặc trạng thái degraded.

Tên event và mức chi tiết phụ thuộc nhà cung cấp. Cần đồng bộ HSM audit với application/KMS audit bằng key label hoặc object ID đã được kiểm soát, session ID, principal, timestamp và request ID nếu có.

Không đưa PIN, authentication secret, private key bytes hoặc backup wrapping key vào log. HSM audit không thay thế kiểm soát vật lý, phân quyền operator và quy trình key ceremony.

## 13. Audit certificate và PKI

Vòng đời certificate có liên hệ với key lifecycle nhưng là một lớp quản lý riêng. Nên audit:

- Tạo key pair và CSR.
- Yêu cầu, phê duyệt và phát hành certificate.
- Certificate serial number, subject/SAN, issuer và validity period.
- Gia hạn, thay certificate và cập nhật trust store.
- Thu hồi certificate, lý do và thời điểm.
- Cập nhật CRL/OCSP hoặc trạng thái revocation theo hệ thống.
- Thay đổi CA, trust anchor và policy cấp phát.

Không ghi private key vào audit. Certificate công khai có thể được ghi fingerprint hoặc serial number để tra cứu; vẫn cần tránh ghi dữ liệu định danh không cần thiết.

Khi private key bị compromise, audit cần giúp liên kết key ID, certificate serial, các lần ký và thời điểm revoke. Thu hồi certificate không tự động xóa mọi bản sao private key, vì vậy cần xử lý key destruction riêng.

## 14. Audit backup và restore key

Backup/restore là thao tác nhạy cảm vì có thể tạo thêm bản sao hoặc tái kích hoạt key đã bị disable. Event nên ghi:

- Backup ID và key ID/version liên quan.
- Actor, approver và recovery role.
- Backend/source, destination và backup domain.
- Cơ chế wrapping/encryption và integrity verification.
- Thời điểm tạo, thời hạn retention và trạng thái.
- Restore target, environment và kết quả kiểm tra.
- Có re-enable hoặc thay đổi policy sau restore hay không.

Không ghi key bytes hoặc recovery secret. Với HSM, dùng quy trình backup chính thức, quorum và security domain theo tài liệu vendor. Với KMS, cần biết key version nào đang bảo vệ backup và key version cũ phải được giữ bao lâu để dữ liệu còn giải mã được.

## 15. Audit rotation và key version

Rotation thường gồm nhiều bước, không phải một thao tác duy nhất. Audit cần ghi:

1. Rotation được yêu cầu, actor và lý do.
2. Key version mới được tạo.
3. Policy và metadata của version mới được xác nhận.
4. Consumer bắt đầu dùng version mới.
5. Dữ liệu mới được mã hóa bằng version mới.
6. Dữ liệu cũ được rewrap/re-encrypt nếu cần.
7. Version cũ chuyển sang decrypt-only hoặc disabled theo policy.
8. Rotation hoàn tất và có bằng chứng consumer đã chuyển đổi.

Không xóa version cũ chỉ vì version mới đã được tạo. Nếu backup hoặc dữ liệu lịch sử vẫn phụ thuộc version cũ, phải giữ khả năng unwrap/decrypt theo retention và recovery policy.

Audit nên có quan hệ giữa old key version, new key version, migration job, consumer và thời điểm cutover. Nhờ đó, điều tra có thể biết dữ liệu nào còn dùng khóa cũ.

## 16. Audit revoke, disable và destruction

Các trạng thái này có ý nghĩa khác nhau:

- **Disable:** ngăn hoặc hạn chế operation trong khi vẫn giữ key material để có thể phục hồi theo policy.
- **Revoke:** thu hồi quyền hoặc trạng thái tin cậy, ví dụ certificate hoặc principal không còn được phép sử dụng.
- **Destroy:** hủy key material hoặc làm mất khả năng sử dụng/khôi phục theo cơ chế backend.

Audit cần ghi actor, key ID/version, lý do, approval, trạng thái trước/sau, thời gian có hiệu lực và kết quả từ backend. Nếu backend hỗ trợ pending deletion window, phải ghi thời điểm schedule và thời điểm destruction hoàn tất.

Không xem API trả về success cho yêu cầu schedule deletion là bằng chứng key đã bị zeroize ngay. Cần phân biệt yêu cầu được chấp nhận, thời gian chờ và xác nhận hoàn tất từ backend.

## 17. Audit truy cập bị từ chối và lỗi kỹ thuật

Phân biệt các kết quả:

| Outcome | Ý nghĩa |
|---|---|
| success | Backend chấp nhận và hoàn tất operation |
| denied | Authorization/policy từ chối request |
| failure | Operation không hoàn tất do lỗi kỹ thuật hoặc trạng thái backend |
| partial | Một phần workflow đã hoàn tất; cần ghi rõ bước và trạng thái |

Denied event có thể báo hiệu principal cố truy cập key ngoài scope. Failure event có thể phản ánh HSM timeout, network issue, quota, key state hoặc parameter không hợp lệ. Không gộp tất cả thành “key access failed”.

Không log request body chứa plaintext, password, token hoặc key bytes. Ghi mã lỗi, operation, key ID, principal, backend và request ID để điều tra.

## 18. Nhận diện principal và nguồn truy cập

Không chỉ ghi username chung như admin hoặc service. Nên dùng danh tính ổn định:

Đối với con người:

- User ID và identity provider.
- Role/group tại thời điểm thao tác.
- MFA/assurance context khi cần.
- Session ID, approval và ticket.

Đối với workload:

- Workload identity hoặc service account ID.
- Cluster, namespace, application và environment.
- Instance/pod hoặc deployment version khi cần.
- Token issuer/audience ở mức metadata.
- Source network hoặc host context phù hợp.

IP address chỉ là ngữ cảnh bổ sung, không phải danh tính chính. NAT, proxy và service mesh có thể làm IP không phản ánh workload thực hiện operation.

## 19. Không ghi key material vào audit

Audit log phải ghi nhận hoạt động, không trở thành nơi lưu thêm bí mật. Tuyệt đối tránh ghi:

- Private key bytes hoặc secret key bytes.
- Plaintext DEK/KEK hoặc dữ liệu sau decrypt.
- Password, PIN, recovery secret hoặc wrapping credential.
- Token có thể sử dụng trực tiếp.
- Ciphertext hoặc payload nhạy cảm nếu không cần cho mục tiêu audit.

Có thể ghi:

- Key ID/version và key purpose.
- Algorithm/profile và operation.
- Principal, provider/backend và policy decision.
- Request ID, approval reference, timestamp và outcome.
- Fingerprint hoặc certificate serial nếu cần tra cứu.

Không tự tạo hash của key material để thay key ID. Nếu fingerprint thực sự cần thiết, dùng định dạng và thuật toán được xác định, đánh giá khả năng suy đoán và không đưa giá trị đó vào log công khai.

## 20. Bảo vệ audit log khỏi sửa đổi

Audit log là bằng chứng điều tra và compliance. Nếu người có quyền sử dụng key cũng có thể sửa hoặc xóa log, họ có thể che giấu hoạt động.

Các biện pháp:

- Gửi event tới hệ thống logging tách biệt với workload và KMS admin domain.
- Dùng append-only hoặc immutable/WORM storage theo retention.
- Tách quyền ghi, đọc, cấu hình, export và xóa log.
- Mã hóa log khi truyền và khi lưu.
- Bảo vệ audit configuration khỏi bị disable.
- Ghi nhận thay đổi destination, retention và event category.
- Đồng bộ thời gian và giám sát clock drift.
- Kiểm tra định kỳ event đã đến kho lưu trữ và SIEM.

Hash chain hoặc chữ ký event có thể giúp phát hiện sửa đổi, nhưng khóa ký và điểm neo phải được quản lý độc lập. Không giả định một hash chain bảo vệ được log nếu cùng một principal kiểm soát cả log store và khóa xác minh.

## 21. Phân quyền truy cập audit

Tách vai trò để tránh một người vừa thực hiện operation trên key vừa xóa bằng chứng:

| Quyền | Vai trò thường cần |
|---|---|
| Emit/write | KMS/HSM gateway, provider hoặc collector được xác thực |
| Search/read | Security analyst, auditor, incident responder theo scope |
| Configure | Security platform owner |
| Export | Người được phê duyệt cho điều tra/compliance |
| Delete/retention override | Quyền đặc biệt, dual control và audit riêng |

KMS administrator không nên mặc nhiên có quyền xóa audit evidence. Ứng dụng runtime không được quyền thay đổi logging destination hoặc retention. Thao tác export key và thay đổi policy nên được tách khỏi quyền sử dụng key thông thường.

## 22. Tích hợp SIEM và phát hiện bất thường

Nguồn audit có thể đến từ KMS, HSM, PKI, IAM, secret manager, ứng dụng và cloud control plane. Pipeline cần chuẩn hóa schema, xác thực nguồn, loại bỏ secret value và gửi đến kho lưu trữ tập trung.

~~~mermaid
flowchart LR
    A["KMS audit"] --> E["Collector / event bus"]
    B["HSM audit"] --> E
    C["IAM / PKI"] --> E
    D["Application / backup"] --> E
    E --> F["Normalize + validate + redact"]
    F --> G["Immutable audit store"]
    F --> H["SIEM / detection rules"]
    H --> I["Alert / incident case"]
    G --> J["Investigation / compliance"]
~~~

Một số tín hiệu cần giám sát:

- Principal sử dụng key ngoài environment hoặc purpose thông thường.
- Decrypt/sign tăng đột biến so với baseline.
- Một key được dùng từ workload hoặc region mới.
- Principal vừa được cấp quyền rộng rồi thực hiện decrypt/export.
- Nhiều lần denied operation trên key production.
- Key version đã disable vẫn bị yêu cầu sử dụng.
- Thao tác export, backup, restore hoặc destruction ngoài change window.
- Rotation thất bại hoặc consumer vẫn dùng version cũ quá thời hạn.
- Audit logging bị disable, event delay tăng hoặc destination bị thay đổi.

Không tạo alert chỉ dựa trên IP hoặc thời gian. Kết hợp principal, key ID/version, operation, volume, policy change, environment và change window để giảm false positive.

## 23. Ví dụ detection rule

Ví dụ pseudocode phát hiện một workload decrypt bất thường:

~~~text
IF
  eventType = "key.decrypt"
  AND principal.type = "workload"
  AND key.purpose = "production-data"
  AND decrypt_count > workload_baseline
  AND NOT approved_restore_or_reprocessing_window
THEN
  alert = "unusual_key_decrypt_volume"
  severity = "high"
  include = [principal.id, key.id, key.version, request_ids]
~~~

Đây là logic minh họa, không phải cú pháp SIEM cụ thể. Baseline phải được xác định theo workload và loại dữ liệu. Backup restore, batch reprocessing hoặc migration có thể tạo volume lớn hợp lệ; các workflow này cần identity riêng và approval/change window.

Một rule khác có thể nối policy update với operation: nếu quyền decrypt vừa được cấp cho principal mới rồi principal đó sử dụng key production mà không có approval, tạo alert có mức ưu tiên cao.

## 24. Baseline và access review

Baseline giúp xác định hành vi sử dụng key bình thường:

- Workload/principal nào dùng key.
- Operation nào được phép.
- Tần suất, volume và khung thời gian.
- Key version thường được dùng.
- Environment, tenant và backend.
- Lịch rotation, backup, restore và batch job.

Baseline cần được cập nhật qua change process. Không tự động chấp nhận mọi hành vi mới, vì kẻ tấn công có thể làm nhiễm baseline.

Trong access review định kỳ, cần xem principal nào có quyền sử dụng key, quyền đó có còn cần thiết không, key có owner không, có workload cũ còn truy cập không và quyền export/delete/admin có bị gộp quá rộng không. Không dùng việc “không thấy event” làm bằng chứng duy nhất rằng quyền không được dùng; có thể backend cache hoặc audit chưa đầy đủ.

## 25. Break-glass và key ceremony

Break-glass là quyền truy cập khẩn cấp khi sự cố không thể xử lý theo quy trình thông thường. Key ceremony là quy trình có kiểm soát để tạo, import, backup hoặc phục hồi khóa quan trọng.

Audit cần ghi:

- Người tham gia và vai trò của từng người.
- Incident/change ID và lý do.
- Approval/quorum hoặc M-of-N requirement.
- Thời điểm mở/đóng phiên và phạm vi quyền.
- Hành động được thực hiện, key ID và kết quả.
- Việc thu hồi quyền tạm thời sau khi hoàn tất.

Không dùng tài khoản operator chung nếu có thể dùng identity riêng. Không ghi PIN hoặc secret của ceremony vào log. Với key quan trọng, tách người khởi tạo, người phê duyệt và người thực hiện theo policy.

## 26. Tương quan sự kiện và đồng bộ thời gian

Điều tra thường cần ghép event từ KMS, HSM, IAM, ứng dụng, PKI và backup platform. Nên:

- Ghi timestamp UTC theo định dạng chuẩn.
- Giữ event time và ingest time riêng.
- Đồng bộ đồng hồ bằng nguồn tin cậy và giám sát clock drift.
- Dùng request ID, trace ID, workflow ID hoặc session ID.
- Dùng key ID/version nhất quán giữa các hệ thống.
- Ghi source system và schema version.

Không ghép event chỉ dựa trên timestamp gần nhau. Khi không có correlation ID, kết hợp principal, key ID, operation, source và thời gian; ghi rõ mức độ chắc chắn của quan hệ.

## 27. Retention và bảo vệ dữ liệu audit

Audit log có thể chứa danh tính, địa chỉ mạng, cấu trúc hạ tầng và thông tin vận hành. Retention cần cân bằng nhu cầu điều tra, compliance và quyền riêng tư.

Policy nên xác định:

- Thời hạn lưu theo loại event và mức độ quan trọng của key.
- Yêu cầu pháp lý, hợp đồng và tiêu chuẩn áp dụng.
- Legal hold và quy trình export evidence.
- Mã hóa log, quyền truy cập và key bảo vệ log.
- Cách xóa an toàn sau khi hết retention.
- Bằng chứng log không bị sửa.
- Cách lưu event khi collector hoặc SIEM tạm thời gián đoạn.

Không giữ mọi log vô thời hạn chỉ vì storage rẻ. Cũng không đặt retention quá ngắn khiến tổ chức không thể điều tra sự cố được phát hiện muộn. Với key có cryptoperiod dài hoặc backup retention dài, cần giữ event đủ để chứng minh key version và operation liên quan.

## 28. Giám sát chính hệ thống audit

Kẻ tấn công có thể tắt audit hoặc làm nghẽn pipeline trước khi sử dụng key. Cần theo dõi:

- Audit logging bị disable hoặc giảm event category.
- Collector ngừng nhận event hoặc event delay vượt ngưỡng.
- Event bị drop, queue backlog hoặc schema validation failure.
- Thay đổi log destination, retention hoặc access policy.
- Authentication failure của collector.
- KMS/HSM audit source bị mất kết nối.
- Event test không xuất hiện trong immutable store hoặc SIEM.

Nếu không thể ghi audit, policy cần quyết định operation nhạy cảm có được tiếp tục hay không. Với thao tác ký hoặc decrypt quan trọng, có thể yêu cầu fail-closed; hệ thống availability cao có thể buffer event an toàn nhưng phải cảnh báo ngay và giới hạn thời gian.

## 29. Incident response khi phát hiện key usage bất thường

Khi có alert, đội phản ứng cần:

1. Xác định principal, key ID/version, operation, backend và outcome.
2. Kiểm tra identity/session có hợp lệ hay bị chiếm quyền.
3. Dựng chuỗi policy change, grant, key use và backup/restore event.
4. Kiểm tra workload, host, deployment, network và request trace.
5. Xác định key material có thể bị export/lộ hay chỉ bị sử dụng trái phép qua backend.
6. Cô lập principal hoặc thu hồi session khi cần.
7. Disable/revoke key theo incident policy, đánh giá ảnh hưởng đến dữ liệu và dịch vụ.
8. Rotate/reissue key hoặc certificate; cập nhật consumer.
9. Kiểm tra dữ liệu/chữ ký/backup có thể bị ảnh hưởng.
10. Bảo toàn audit evidence và ghi timeline, quyết định, phạm vi.

Nếu private key bị compromise, cần đánh giá certificate revocation và các chữ ký phát sinh trong khoảng thời gian nghi ngờ. Nếu KEK bị lộ, phải đánh giá DEK đã được bọc bởi KEK đó và backup/data object liên quan. Nếu chỉ một principal có quyền quá rộng, thu hồi identity/policy có thể là bước đầu nhưng vẫn cần kiểm tra operation đã diễn ra.

## 30. Kiểm thử audit control

Không nên chờ sự cố mới kiểm tra audit. Dùng key và identity thử để xác minh:

| Test | Kết quả mong đợi |
|---|---|
| Generate key | Có event actor, key ID, algorithm, purpose và outcome |
| Encrypt/decrypt | Có event operation, principal, key version và request ID |
| Sign/verify | Có event phù hợp với backend và key ID |
| Denied operation | Có event deny và policy reason |
| Policy update | Có actor, policy version trước/sau và approval |
| Rotation | Có version cũ/mới, migration state và completion |
| Backup/restore | Có backup ID, key version, approver và target |
| Disable/revoke | Có actor, lý do, trạng thái và kết quả |
| Destruction | Có schedule, waiting period và confirmation |
| Audit outage | Có alert hoặc buffer/gap detection |

Kiểm thử cần xác minh cả event tại nguồn, collector, immutable store và SIEM. Không dùng key production hoặc dữ liệu khách hàng thật để tạo test event.

## 31. Ví dụ triển khai: audit key cho dịch vụ mã hóa dữ liệu

Một dịch vụ lưu hồ sơ khách hàng dùng envelope encryption:

1. Workload identity xác thực với KMS.
2. KMS tạo DEK và ghi event GenerateDataKey gắn với KEK ID/version.
3. Ứng dụng dùng plaintext DEK trong bộ nhớ để mã hóa dữ liệu bằng AES-GCM.
4. Ứng dụng lưu ciphertext, wrapped DEK và metadata format version.
5. Ứng dụng phát event metadata cho operation mã hóa, gồm object ID, key ID/version, request ID và outcome.
6. Khi đọc dữ liệu, workload yêu cầu KMS unwrap DEK; KMS audit ghi principal và key version.
7. Rotation tạo KEK version mới; dữ liệu mới dùng version mới, dữ liệu cũ được rewrap theo kế hoạch.
8. Version cũ chỉ bị disable hoặc destroy khi không còn backup/data object cần nó.
9. SIEM cảnh báo nếu workload decrypt vượt baseline hoặc principal lạ dùng KEK.

Thiết kế không ghi DEK hoặc plaintext vào log. KMS audit chứng minh operation trên KEK; application audit cung cấp ngữ cảnh object và operation nghiệp vụ. Hai nguồn cần được liên kết bằng request ID và key version.

## 32. Checklist thiết kế Key management audit

Trước khi đưa audit vào production, hãy xác nhận:

- [ ] Đã có inventory key ID, owner, purpose, environment, backend và version.
- [ ] Đã xác định nguồn audit từ KMS, HSM, PKI, provider, ứng dụng và backup.
- [ ] Ghi cả control-plane và data-plane events.
- [ ] Có event cho generate, import, policy, use, backup, restore, rotate, revoke và destroy.
- [ ] Event xác định principal, key ID/version, operation, provider, timestamp và outcome.
- [ ] Có policy decision, approval/ticket và request/correlation ID cho thao tác nhạy cảm.
- [ ] Ghi denied và failure riêng biệt.
- [ ] Không ghi key material, plaintext DEK, password, PIN hoặc token.
- [ ] Audit log được gửi tới miền lưu trữ tách biệt và chống sửa đổi.
- [ ] Quyền emit, read, configure, export và delete log được tách biệt.
- [ ] Thay đổi audit configuration và retention cũng được ghi nhận.
- [ ] SIEM có baseline và detection cho decrypt/sign/export bất thường.
- [ ] Rotation event liên kết version cũ/mới và consumer migration.
- [ ] Backup/restore event liên kết key version và recovery approval.
- [ ] Break-glass/key ceremony có identity riêng, quorum và audit đầy đủ.
- [ ] Retention phù hợp cryptoperiod, backup retention và yêu cầu điều tra.
- [ ] Có test cho allow, deny, rotate, restore, revoke, destroy và audit outage.
- [ ] Có incident response để cô lập principal, xử lý key compromise và bảo toàn evidence.

## 33. Checklist điều tra một key operation bất thường

Khi nhận alert, hãy xác nhận:

- [ ] Principal và session có đúng owner không?
- [ ] Key ID/version và purpose nào đã được sử dụng?
- [ ] Operation là encrypt, decrypt, sign, unwrap, export hay lifecycle change?
- [ ] Request được allow, deny hay failure?
- [ ] Policy hoặc role có vừa thay đổi không?
- [ ] Có approval/change/restore window hợp lệ không?
- [ ] Provider/backend và source workload có đúng không?
- [ ] Có operation tiếp theo hoặc downstream impact không?
- [ ] Key material có thể đã bị export/lộ hay chỉ bị gọi operation?
- [ ] Đã disable/revoke/rotate key hoặc identity cần thiết chưa?
- [ ] Backup, certificate và dữ liệu lịch sử còn phụ thuộc key version nào?
- [ ] Audit evidence đã được bảo toàn và timeline đã được dựng chưa?

Key management audit tạo bằng chứng xuyên suốt vòng đời khóa, từ lúc tạo đến khi hủy. Muốn audit có giá trị, cần xác định chính xác principal, key ID/version, operation, policy decision và kết quả; bao phủ cả thay đổi cấu hình lẫn thao tác mật mã; bảo vệ log khỏi sửa đổi; đồng thời không đưa key material vào log. Kết hợp audit của KMS/HSM, PKI, ứng dụng và backup platform giúp tổ chức phát hiện việc sử dụng khóa bất thường, điều tra compromise và duy trì khả năng khôi phục dữ liệu có kiểm soát.
