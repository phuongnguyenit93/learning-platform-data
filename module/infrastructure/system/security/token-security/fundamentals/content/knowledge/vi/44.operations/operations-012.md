# Backup token metadata: sao lưu và phục hồi trạng thái token an toàn

## 1. Bối cảnh và mục tiêu

Hệ thống OAuth 2.0/OIDC lưu nhiều dữ liệu trạng thái để quản lý vòng đời token: grant, client, subject, scope, audience, thời hạn, trạng thái thu hồi, quan hệ refresh token rotation và dấu vết phát hiện replay. Dữ liệu này quyết định resource server có chấp nhận token hay không. Nếu database hỏng, bị xóa nhầm hoặc bị mã hóa bởi ransomware, hệ thống cần khôi phục metadata mà vẫn giữ nguyên các quyết định bảo mật đã có trước sự cố.

**Backup token metadata** là quá trình tạo bản sao có kiểm soát của dữ liệu cần thiết để phục hồi trạng thái token và quyền truy cập. Phạm vi backup phải phân biệt metadata với bearer secret. Authorization server thường chỉ cần fingerprint/hash của opaque token cùng metadata; backend OAuth client có thể phải lưu ciphertext của refresh token vì cần khôi phục giá trị để gọi token endpoint. Khóa mã hóa, signing key và dữ liệu bí mật có vòng đời quản lý riêng.

Trong nền tảng **Security Token Security Fundamentals**, bài này gắn backup với mô hình tin cậy và vòng đời JWT, opaque token, access token, refresh token, OAuth 2.0/OIDC, thu hồi và phòng chống replay. Một bản backup khôi phục được database nhưng làm sống lại refresh token đã bị thu hồi vẫn là một lần phục hồi thất bại về mặt bảo mật.

Sau bài này, người học có thể:

- Xác định metadata nào cần backup ở authorization server, resource server và OAuth client.
- Thiết kế backup nhất quán cho grant, token family, revocation state và audit/event log.
- Thiết lập RPO, RTO, retention, mã hóa và quyền truy cập backup.
- Phục hồi theo thời điểm mà không làm sống lại token đã consumed hoặc revoked.
- Phối hợp dữ liệu ciphertext với KMS/key version và quy trình khôi phục khóa.
- Kiểm thử restore, disaster recovery và các tình huống rollback có rủi ro bảo mật.

## 2. Phân biệt metadata và bí mật token

Trước khi lập chính sách backup, lập danh mục dữ liệu theo vai trò của thành phần.

| Thành phần | Dữ liệu cần phục hồi | Dữ liệu nhạy cảm và cách xử lý |
| --- | --- | --- |
| Authorization server | Client registration, grant/consent, token ID, fingerprint token, family, generation, trạng thái active/consumed/revoked, expiry và revocation record. | Không cần backup raw opaque refresh token nếu AS chỉ tra cứu bằng hash/fingerprint. Mã hóa backup vì metadata vẫn nhạy cảm. |
| Resource server | Policy, issuer/audience configuration, cache state nếu cần, denylist hoặc revocation state do ứng dụng quản lý. | Không backup bearer token từ log/cache như dữ liệu thường. Cache có thể được tái tạo nếu nguồn trạng thái có thẩm quyền còn nguyên. |
| Backend OAuth client / BFF | Liên kết session/credential, trạng thái refresh operation và metadata để chọn credential. | Nếu cần khôi phục refresh token, chỉ backup ciphertext, nonce/tag, wrapped DEK, key version và AAD metadata. Không lưu plaintext vào bản backup. |
| Mobile client | Thường không nằm trong backup server-side của ứng dụng. | Token được bảo vệ bởi secure storage của thiết bị và chính sách backup của hệ điều hành. Không xuất token thiết bị vào backup tập trung. |
| Key management | Key ID/version, policy, alias, quyền và cấu hình phục hồi. | Key material được bảo vệ theo KMS/HSM; không chép private key hoặc KEK vào cùng database backup. |

### 2.1. Metadata thường cần lưu

Với opaque token hoặc refresh token được quản lý trạng thái, các trường thường cần gồm:

- Định danh nội bộ của token và `family_id`.
- Fingerprint/hash token nếu cần tra cứu token do client gửi.
- `client_id`, subject reference và grant/session reference.
- Scope, resource/audience và sender constraint nếu có.
- `issued_at`, `expires_at`, `last_used_at`, `consumed_at`, `revoked_at`.
- Trạng thái token, generation, parent token và token successor.
- Lý do thu hồi, nguồn thu hồi, mốc sự kiện và audit reference.

Không phải hệ thống nào cũng cần mọi trường. Chỉ giữ dữ liệu có mục đích rõ ràng và retention được phê duyệt. Subject reference, family ID và token fingerprint vẫn có thể liên kết hoạt động người dùng; backup của chúng cần được phân loại và bảo vệ như dữ liệu nhạy cảm.

### 2.2. JWT và trạng thái thu hồi

JWT access token có thể được xác minh bằng chữ ký và claims mà không cần truy vấn database cho từng request. Tuy nhiên, nếu hệ thống hỗ trợ thu hồi trước `exp`, denylist, session state, grant state hoặc key version vẫn có thể là dữ liệu quan trọng cần backup.

Không backup raw JWT từ access log để phục hồi quyền truy cập. Với JWT, cần bảo vệ metadata thu hồi và tham chiếu tới signing key version. Private signing key phải được quản lý riêng trong KMS/HSM hoặc hệ thống key management được kiểm soát. Public JWKS có thể được tái công bố từ nguồn tin cậy; việc phục hồi public key không thay thế khả năng bảo vệ private key.

### 2.3. Hash và ciphertext không có cùng mục đích

- **Hash/fingerprint:** authorization server dùng để nhận diện token khi token có entropy cao. Hash không thể dùng để gửi token trở lại token endpoint.
- **Ciphertext:** OAuth client dùng để khôi phục refresh token đã mã hóa. Ciphertext phải đi cùng nonce, authentication tag, AAD cần thiết và wrapped DEK/key version.
- **Plaintext bearer token:** không đưa vào backup, export, snapshot chẩn đoán hoặc kho lưu trữ thông thường.

Hash token không phải dữ liệu vô hại. Nó có thể dùng để liên kết các bản ghi và hỗ trợ dò tìm nếu token entropy yếu. Luôn mã hóa backup và hạn chế quyền truy cập.

## 3. Rủi ro khi backup hoặc restore token metadata

Backup không đúng có thể làm hỏng tính nhất quán bảo mật theo nhiều cách:

| Rủi ro | Ví dụ | Hậu quả |
| --- | --- | --- |
| Phục hồi trạng thái cũ | Snapshot trước khi refresh token bị revoke được restore sau sự cố. | Token đã thu hồi có thể xuất hiện lại ở trạng thái active. |
| Mất sự kiện mới hơn snapshot | Database được restore nhưng audit/revocation event sau thời điểm backup không được replay. | Denylist, family revoke hoặc consent mới bị mất. |
| Backup không nhất quán | Token record được backup nhưng token family hoặc grant liên quan không được backup cùng mốc. | Quan hệ parent/successor hoặc trạng thái family bị sai. |
| Mất khóa giải mã | Ciphertext còn nhưng KEK/DEK hoặc key version không thể truy cập. | Client không thể khôi phục refresh token để tiếp tục phiên. |
| Khôi phục credential client cũ | BFF restore ciphertext chứa refresh token đã bị rotation và consumed. | Request tiếp theo gây `invalid_grant` hoặc kích hoạt reuse detection. |
| Backup bị lộ | Backup chứa subject, scope, token fingerprint, client và session metadata. | Lộ thông tin định danh, quan hệ và bề mặt tấn công nội bộ. |
| Ransomware phá backup | Backup cùng tài khoản/quyền với production bị xóa hoặc mã hóa. | Không còn điểm phục hồi tin cậy. |

**Replication không thay thế backup.** Lỗi xóa dữ liệu, sửa trạng thái token hoặc ransomware có thể được nhân bản sang replica. Cần bản backup độc lập, bất biến hoặc khó sửa/xóa, cùng quy trình restore đã kiểm chứng.

## 4. Xác định phạm vi và mục tiêu phục hồi

### 4.1. Xác định nguồn dữ liệu có thẩm quyền

Với mỗi loại dữ liệu, ghi rõ nguồn sự thật:

- Authorization server database giữ trạng thái grant, refresh token family và token revocation.
- Event/audit log có thể lưu sự kiện phát hành, rotation, revoke, logout và admin action.
- Resource server có thể giữ denylist cục bộ hoặc cache, nhưng thường cần tái tạo từ nguồn trạng thái có thẩm quyền.
- Client credential store giữ ciphertext của refresh token và liên kết với session/user.
- KMS/HSM quản lý key material, key version và quyền giải mã.

Không mặc định rằng restore database chính là restore toàn bộ hệ thống token. Cần khôi phục đúng các nguồn liên quan và xác nhận quan hệ giữa chúng.

### 4.2. Đặt RPO và RTO

**Recovery Point Objective (RPO)** là lượng dữ liệu tối đa có thể mất tính theo thời gian. **Recovery Time Objective (RTO)** là thời gian mục tiêu để khôi phục dịch vụ. Với metadata token, RPO ảnh hưởng trực tiếp đến độ mới của trạng thái thu hồi.

Ví dụ minh họa:

| Dữ liệu | RPO tham khảo | Lý do |
| --- | --- | --- |
| Refresh token family và revocation state | Gần zero hoặc vài phút tùy kiến trúc. | Mất trạng thái mới có thể làm sống lại token đã revoke/consumed. |
| Grant và consent | Theo RPO của authorization service. | Mất grant có thể khiến người dùng phải cấp quyền lại; khôi phục sai có thể mở quyền đã thu hồi. |
| Client encrypted credentials | Theo mức chấp nhận được của phiên BFF. | Restore bản cũ có thể chứa refresh token đã bị consume. |
| Audit/event log | Liên tục hoặc đủ dày để replay sau snapshot. | Cần điều tra và tái áp dụng sự kiện bảo mật mới hơn backup. |
| Dashboard/cache có thể tái tạo | Theo khả năng tái tạo. | Không phải nguồn sự thật cho quyết định xác thực. |

Các con số cụ thể phải dựa trên threat model, lưu lượng, SLA và khả năng của storage. Đừng đặt RPO dài cho revocation state nếu hệ thống yêu cầu token bị thu hồi phải mất hiệu lực nhanh.

### 4.3. Chọn chiến lược backup

| Phương pháp | Ưu điểm | Điều cần kiểm soát |
| --- | --- | --- |
| Full backup | Khôi phục độc lập, dễ hiểu. | Dung lượng, thời gian tạo và bảo vệ bản sao. |
| Incremental/differential | Giảm thời gian và dung lượng giữa các full backup. | Chuỗi phụ thuộc; phải kiểm tra đủ các phần để restore. |
| Point-in-time recovery (PITR) | Khôi phục database tới mốc cụ thể bằng transaction log/WAL. | Log phải liên tục, được giữ đủ lâu và đồng bộ với backup base. |
| Event replay | Áp dụng sự kiện sau snapshot để dựng lại trạng thái mới hơn. | Event phải có thứ tự, idempotency, integrity và retention phù hợp. |
| Cross-region backup | Hỗ trợ sự cố vùng hoặc tài khoản hạ tầng. | Key, IAM, network, DNS và quy trình failover cũng phải sẵn sàng ở vùng phục hồi. |

Kết hợp full backup định kỳ với PITR hoặc event replay thường cho khả năng phục hồi tốt hơn chỉ giữ một bản snapshot gần nhất. Tuy nhiên, event log không thay thế database backup nếu không có quy trình dựng lại toàn bộ trạng thái và kiểm chứng tính đầy đủ.

## 5. Thiết kế backup nhất quán

### 5.1. Tạo mốc nhất quán

Backup phải phản ánh một mốc dữ liệu có thể xác định. Với database hỗ trợ snapshot nhất quán, dùng cơ chế native backup/PITR của database. Nếu token metadata nằm ở nhiều store, ghi nhận checkpoint hoặc watermark cho từng nguồn.

Manifest backup nên ghi tối thiểu:

```yaml
backup_id: token-state-2026-11-23T020000Z
created_at: 2026-11-23T02:00:00Z
source_system: authorization-server
database_snapshot: snapshot-reference
transaction_log_position: wal-or-lsn-position
event_checkpoint: event-sequence
schema_version: 12
encryption_key_version: token-backup-kek-v4
integrity_digest: sha256-digest-reference
retention_until: 2026-12-23T02:00:00Z
```

Đây là cấu trúc minh họa; không đưa secret, token hoặc thông tin xác thực KMS vào manifest. Manifest cần được ký hoặc bảo vệ integrity theo cơ chế của nền tảng backup.

### 5.2. Quan hệ giữa token và family

Nếu refresh token được lưu theo family, backup phải giữ nhất quán:

- Token record và trạng thái `ACTIVE`, `CONSUMED`, `REVOKED`, `EXPIRED`.
- Family record và generation hiện hành.
- Quan hệ parent/successor.
- Client, subject, grant và sender constraint.
- Revocation event và mốc thời gian liên quan.

Sau restore, kiểm tra invariant: mỗi family chỉ có số token active phù hợp với mô hình; token consumed không trở thành active; successor có parent hợp lệ; family revoked không có token active được chấp nhận.

### 5.3. Đồng bộ audit và revocation event

Giả sử database snapshot ở thời điểm T1, nhưng user revoke family ở T2. Nếu restore snapshot T1 mà không replay sự kiện T2, token có thể sống lại. Có ba cách thường dùng:

1. Dùng PITR để đưa database tới thời điểm sau T2 nếu transaction log còn nguyên.
2. Restore snapshot T1 rồi replay revocation/audit event từ sau T1 theo thứ tự, bảo đảm event không bị mất và replay idempotent.
3. Nếu không thể chứng minh dữ liệu revocation đầy đủ, revoke các family/grant nằm trong phạm vi không chắc chắn hoặc yêu cầu người dùng cấp quyền lại.

Không lấy audit log chỉ để hiển thị rồi bỏ qua khi restore. Nếu log được dùng để tái áp dụng trạng thái, nó phải có integrity, thứ tự, checkpoint và quy trình replay được kiểm thử.

## 6. Bảo vệ backup và quyền truy cập

Backup token metadata vẫn là dữ liệu bảo mật. Áp dụng defense in depth:

- Mã hóa khi truyền và khi lưu; dùng thuật toán và dịch vụ mã hóa được quản lý.
- Dùng khóa backup riêng hoặc key hierarchy rõ ràng; không dùng chung một key plaintext trong file cấu hình.
- Tách quyền tạo backup, đọc backup, xóa backup và phục hồi. Không cấp tất cả quyền cho một workload role.
- Dùng tài khoản/project/storage account riêng cho backup; giới hạn đường mạng và danh tính có thể truy cập.
- Bật immutability/WORM hoặc retention lock cho bản backup quan trọng.
- Lưu bản sao cross-account/cross-region theo threat model.
- Ghi audit cho thao tác download, restore, delete, thay retention và thay key.
- Kiểm tra checksum/integrity trước khi restore; giữ manifest và metadata phiên bản schema.
- Không dùng backup production để tạo môi trường dev/test có dữ liệu thật; nếu cần dữ liệu kiểm thử, phải làm sạch hoặc tạo dữ liệu giả.

Backup không nên chứa raw access token, raw refresh token, client secret hoặc private signing key. Nếu backup cần ciphertext của refresh token phía client, phải bảo vệ ciphertext và wrapped DEK như credential nhạy cảm, đồng thời giữ KMS access tách biệt.

## 7. KMS, encryption key và signing key

Metadata backup có thể phụ thuộc vào khóa ở nhiều hệ thống:

| Loại khóa | Vai trò | Kế hoạch phục hồi |
| --- | --- | --- |
| Backup KEK | Mã hóa DEK dùng bảo vệ bản backup. | KMS/HSM phải có key version và quyền giải mã tại vùng DR; thử restore bằng danh tính DR. |
| Token storage KEK | Bọc DEK mã hóa refresh token phía OAuth client. | Giữ key version cũ cho tới khi toàn bộ ciphertext và backup phụ thuộc đã migrate/hết retention. |
| HMAC pepper | Tạo fingerprint token ở authorization server nếu được dùng. | Khôi phục key ID/version qua KMS; không lưu pepper cùng database backup. |
| JWT signing private key | Ký JWT do issuer phát hành. | Bảo vệ riêng trong HSM/KMS; chỉ restore/activate theo quy trình key management, không nhập private key vào backup database. |
| JWT public key/JWKS | Cho verifier kiểm tra chữ ký. | Có thể tái công bố từ issuer metadata tin cậy; giữ lịch sử key ID/version cần cho token còn hiệu lực. |

Không xóa key cũ chỉ vì key mới đã được tạo. Backup cũ có thể cần key version cũ để giải mã. Ngược lại, không giữ key cũ hoạt động vô thời hạn nếu đã bị compromise; khi đó cần quy trình thay key, revoke token và chấp nhận yêu cầu xác thực lại phù hợp.

Nếu KMS vùng chính không khả dụng, vùng DR phải có quyền sử dụng key theo policy được phê duyệt. Kiểm tra cả IAM role, network endpoint, key policy, quota và audit trail. Một backup ciphertext tốt nhưng không có khả năng giải mã trong vùng DR không phải bản backup có thể phục hồi.

## 8. Quy trình restore an toàn

Restore token metadata phải có các bước kiểm soát trước khi hệ thống nhận traffic xác thực thật.

### Bước 1 — Cô lập và đánh giá

1. Xác định nguyên nhân sự cố: lỗi thao tác, corruption, ransomware, mất vùng, lỗi migration hay compromise credential.
2. Chọn recovery point và xác định các sự kiện revoke/rotation phát sinh sau mốc đó.
3. Cô lập môi trường restore khỏi traffic production và token endpoint public.
4. Xác minh backup manifest, integrity digest, schema version, nguồn và thời điểm snapshot.
5. Xác nhận KMS/HSM và các key version cần thiết có thể truy cập theo quyền DR.

### Bước 2 — Khôi phục dữ liệu

1. Restore database vào môi trường cô lập.
2. Áp dụng transaction log/PITR tới recovery point đã chọn.
3. Replay event sau checkpoint nếu quy trình event sourcing/revocation yêu cầu.
4. Khôi phục metadata family, grant, client registration và key reference theo đúng schema.
5. Khôi phục ciphertext credential phía client nếu phạm vi DR yêu cầu; không giải mã hàng loạt ra file tạm.

### Bước 3 — Đối soát trạng thái bảo mật

Kiểm tra ít nhất:

- Token/family đã revoked trước và sau recovery point vẫn bị từ chối.
- Token consumed không trở lại active.
- Family không có hai successor active do mất transaction hoặc replay event.
- Grant/consent đã thu hồi không được phục hồi thành quyền đang cấp.
- Token expiry, idle lifetime và absolute lifetime vẫn được tính theo thời gian đáng tin cậy.
- Denylist/revocation state của JWT được tái tạo hoặc đồng bộ.
- Refresh credential phía client khớp với trạng thái hiện tại của AS; không gửi credential cũ để “thử xem còn dùng được không”.
- Key version, KMS policy và ciphertext authentication tag hoạt động đúng.

### Bước 4 — Chạy kiểm thử trong môi trường cô lập

Chạy smoke test với token giả hoặc fixture dành cho DR: token active, inactive, revoked, consumed, expired; refresh rotation; introspection; JWT signature validation; client credential decrypt; và event replay. Xác nhận log/metric không chứa token.

### Bước 5 — Mở traffic có kiểm soát

Chỉ mở traffic sau khi security owner và service owner xác nhận đối soát trạng thái. Có thể mở theo từng instance hoặc nhóm client, theo dõi `invalid_grant`, introspection failure, reuse detection, token validation failure, KMS error và API 401/403. Nếu có dấu hiệu trạng thái token bị hồi sinh, dừng rollout và áp dụng revoke/re-authentication cho phạm vi bị ảnh hưởng.

## 9. Xử lý trường hợp restore làm sống lại token cũ

Đây là rủi ro quan trọng nhất khi phục hồi snapshot cũ. Ví dụ:

1. Tại T1, refresh token `RT-1` còn active và được backup.
2. Tại T2, client dùng `RT-1`, server consume token và phát hành `RT-2`.
3. Tại T3, `RT-2` bị revoke do logout hoặc phát hiện compromise.
4. Tại T4, hệ thống restore snapshot T1.

Nếu chỉ restore database T1, `RT-1` có thể trở lại active và `RT-2`/revocation tại T3 biến mất. Kẻ có bản sao `RT-1` có thể thử refresh lại.

Các biện pháp:

- PITR hoặc replay đầy đủ các event rotation/revocation sau T1.
- Giữ revocation ledger độc lập với database chính nếu threat model yêu cầu.
- Nếu event history không đầy đủ, revoke family/grant thuộc khoảng không chắc chắn hoặc yêu cầu đăng nhập lại cho phạm vi đó.
- Tăng giám sát reuse detection trong thời gian sau restore.
- Không reset trạng thái token cũ về active bằng script sửa dữ liệu thủ công.

Đối với JWT access token đã ký, restore metadata không làm thay đổi chữ ký. Tuy nhiên, nếu hệ thống dùng denylist hoặc key revocation để vô hiệu hóa JWT trước `exp`, phải bảo đảm dữ liệu đó cũng được khôi phục. Nếu private signing key bị compromise, chỉ restore database không giải quyết được vấn đề; cần thay key và xử lý token đã phát hành theo incident plan.

## 10. Runbook backup định kỳ

Một quy trình backup có thể chuẩn hóa theo lịch:

### Trước khi chạy

1. Kiểm tra health database, replication lag và dung lượng lưu trữ.
2. Xác nhận KMS/key version hoạt động, backup role có quyền tối thiểu và retention policy đúng.
3. Xác định checkpoint database và event log.
4. Xác nhận không có migration/schema change chưa tương thích với restore procedure.

### Khi chạy

1. Tạo snapshot/full backup hoặc backup incremental theo lịch.
2. Thu transaction log/WAL để hỗ trợ PITR.
3. Lưu checkpoint cho event/revocation log.
4. Mã hóa backup, tạo integrity digest/manifest và chuyển bản sao tới vùng lưu trữ độc lập.
5. Áp dụng retention lock/immutability theo chính sách.
6. Ghi nhận backup ID, size, duration, kết quả, key version và vị trí lưu.

### Sau khi chạy

1. Xác minh job thành công và mọi object/segment cần thiết đã tồn tại.
2. Kiểm tra checksum hoặc cơ chế integrity.
3. Cảnh báo nếu backup trễ hơn RPO hoặc transaction log bị đứt đoạn.
4. Chọn mẫu backup để restore test định kỳ trong môi trường cô lập.
5. Xóa bản hết retention theo quy trình có audit và bảo đảm không xóa nhầm bản đang bị legal hold.

Backup job thành công chỉ chứng minh dữ liệu đã được ghi. Restore test mới chứng minh dữ liệu có thể đọc, giải mã và dựng lại trạng thái đúng.

## 11. Ransomware và compromise backup

Nếu nghi ngờ backup hoặc credential backup bị compromise:

- Cô lập danh tính, access key và workload role liên quan; kiểm tra audit log của storage/KMS.
- Giữ nguyên bản backup bất biến để điều tra, không overwrite bằng bản mới chưa xác minh.
- Chọn recovery point trước thời điểm compromise đã được xác định, rồi đối chiếu event log độc lập.
- Thay credential backup và key theo quy trình KMS; không tái sử dụng secret nghi bị lộ.
- Nếu token metadata hoặc revocation state có thể bị sửa, xác minh lại grant/family và cân nhắc revoke/re-authentication theo phạm vi.
- Kiểm tra bản sao cross-account/cross-region có bị xóa hoặc thay đổi hay không.
- Ghi lại chain of custody và người phê duyệt các thao tác restore.

Không dùng backup gần nhất chỉ vì nó mới nhất. Bản gần nhất có thể đã bị attacker thay đổi hoặc chứa trạng thái bị thao túng.

## 12. Observability và audit

Metric backup/restore nên phản ánh khả năng phục hồi mà không đưa token hoặc subject vào label:

| Metric/event | Ý nghĩa |
| --- | --- |
| `token_metadata.backup.success` | Backup hoàn tất và manifest đã ghi nhận. |
| `token_metadata.backup.failure` | Backup thất bại theo loại lỗi bounded. |
| `token_metadata.backup.age` | Tuổi của backup gần nhất so với RPO. |
| `token_metadata.backup.duration` | Thời gian tạo backup. |
| `token_metadata.restore.duration` | Thời gian restore tới trạng thái sẵn sàng. |
| `token_metadata.restore.validation.failure` | Lỗi đối soát family, grant, revocation hoặc key. |
| `token_metadata.event_replay.lag` | Độ trễ sự kiện chưa replay sau snapshot. |
| `token_metadata.key_version.remaining` | Số bản ghi/backup còn phụ thuộc key version cũ. |

Audit nên ghi backup ID, recovery point, schema version, key version, người/role thực hiện, phê duyệt, kết quả integrity check, event checkpoint và phạm vi dữ liệu được phục hồi. Không ghi raw access token, refresh token, client secret, private key hoặc plaintext sau giải mã.

Cảnh báo khi backup age vượt RPO, transaction log không liên tục, backup integrity fail, KMS không khả dụng, restore test thất bại, event replay lag tăng hoặc phát hiện token family trở lại active bất thường sau restore.

## 13. Ma trận kiểm thử backup và restore

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| BAK-01 | Full backup metadata có token family. | Manifest, schema version và checkpoint được lưu. |
| BAK-02 | PITR tới thời điểm sau revoke. | Token/family đã revoke vẫn bị từ chối. |
| BAK-03 | Restore snapshot cũ rồi replay revoke event. | Trạng thái revoke được áp dụng lại đúng một lần. |
| BAK-04 | Restore snapshot nhưng thiếu event log. | Không mở traffic; đánh dấu phạm vi không thể chứng minh trạng thái và revoke/re-auth theo policy. |
| BAK-05 | Token consumed trước snapshot. | Không trở lại active sau restore. |
| BAK-06 | Rotation giữa hai checkpoint. | Parent/successor và generation nhất quán. |
| BAK-07 | Hai token active trong cùng family do dữ liệu lỗi. | Restore validation phát hiện invariant violation và chặn mở traffic. |
| BAK-08 | Ciphertext client credential cùng wrapped DEK. | Giải mã được trong môi trường DR với key version hợp lệ; plaintext không ghi ra log. |
| BAK-09 | KMS key version cũ không khả dụng. | Restore báo lỗi rõ ràng; không bỏ qua xác thực AEAD. |
| BAK-10 | Ciphertext hoặc authentication tag bị sửa. | Integrity/authentication thất bại; không sử dụng plaintext. |
| BAK-11 | Backup bị thay đổi sau khi tạo. | Manifest/checksum/signature phát hiện sai lệch. |
| BAK-12 | Restore database cũ có JWT denylist. | Denylist/revocation state được khôi phục hoặc tái tạo đầy đủ. |
| BAK-13 | Backup role cố tải hoặc xóa bản sao ngoài quyền. | Access bị từ chối và audit ghi nhận. |
| BAK-14 | Ransomware mô phỏng trên storage chính. | Bản sao immutable/cross-account vẫn khôi phục được. |
| BAK-15 | Khôi phục client store cũ chứa refresh token đã rotate. | Credential được đối soát với AS; không gửi token cũ mù quáng. |
| BAK-16 | Backup age vượt RPO hoặc WAL bị đứt. | Alert được kích hoạt và backup không được đánh dấu recoverable. |

Kiểm thử restore cần chạy định kỳ trên môi trường cô lập với dữ liệu giả hoặc đã làm sạch. Không chỉ kiểm tra file tồn tại hoặc database khởi động được; phải kiểm tra quyết định xác thực và thu hồi sau phục hồi.

## 14. Checklist vận hành

- [ ] Phân loại dữ liệu theo authorization server, resource server và OAuth client.
- [ ] Không backup plaintext access token, refresh token, client secret hoặc private signing key.
- [ ] Backup token family, grant, consent, fingerprint và revocation metadata theo mốc nhất quán.
- [ ] Ghi manifest gồm backup ID, schema version, checkpoint, key version và integrity reference.
- [ ] RPO/RTO phù hợp với tốc độ thu hồi và rotation token.
- [ ] Có full/incremental backup và PITR/event replay theo kiến trúc dữ liệu.
- [ ] Backup được mã hóa, kiểm tra integrity, immutability và tách quyền truy cập.
- [ ] KMS/HSM và key version cần thiết có thể truy cập ở vùng DR.
- [ ] Restore không làm sống lại token revoked/consumed hoặc grant đã thu hồi.
- [ ] Client ciphertext được đối soát với trạng thái AS trước khi dùng refresh token.
- [ ] Có quy trình xử lý khi event log thiếu hoặc trạng thái sau restore không thể chứng minh.
- [ ] Restore test kiểm tra cả token active, inactive, revoked, expired và key failure.
- [ ] Metric/audit không chứa bearer token hoặc dữ liệu nhạy cảm không cần thiết.
- [ ] Backup và restore được diễn tập, có owner, approval và audit trail.

**Ghi nhớ:** Backup token metadata thành công phải bảo toàn cả dữ liệu và quyết định bảo mật. Khi restore một snapshot cũ, luôn đối chiếu rotation/revocation event sau checkpoint; nếu không thể chứng minh trạng thái hiện tại, cần thu hồi hoặc cấp quyền lại cho phạm vi bị ảnh hưởng thay vì để token cũ hoạt động trở lại.

## Tài liệu đối chiếu

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token và authorization grant.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): thu hồi token tại authorization server.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): truy vấn trạng thái token của resource server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ refresh token, rotation và phát hiện replay.
- [NIST SP 800-34 Rev. 1 — Contingency Planning Guide](https://csrc.nist.gov/pubs/sp/800/34/r1/final): kế hoạch dự phòng và phục hồi hệ thống thông tin.
- [NIST SP 800-57 Part 1 Rev. 5](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): quản lý vòng đời và bảo vệ khóa mật mã.
- [NIST SP 800-209 — Security Guidelines for Storage Infrastructure](https://csrc.nist.gov/pubs/sp/800/209/final): hướng dẫn bảo mật hạ tầng lưu trữ.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): bảo vệ, quản lý và rotation secret.
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html): mã hóa dữ liệu lưu trữ và quản lý khóa.
