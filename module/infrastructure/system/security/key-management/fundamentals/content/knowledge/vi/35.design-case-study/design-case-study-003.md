# Thiết kế key rotation không downtime

Key rotation không downtime là quá trình thay thế khóa mật mã đang được hệ thống sử dụng mà vẫn duy trì khả năng phục vụ request trong suốt quá trình chuyển đổi. Thiết kế này cho phép các phiên bản ứng dụng đang chạy đọc được dữ liệu cũ và mới, chuyển hoạt động ghi sang khóa mới theo kế hoạch, di chuyển dữ liệu còn phụ thuộc khóa cũ, rồi thu hồi khóa cũ sau khi đã chứng minh không còn nhu cầu sử dụng.

Trong module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, key rotation không downtime kết nối vòng đời khóa với KMS/HSM, envelope encryption, quyền truy cập, versioning, backup/recovery, audit và vận hành production. Không downtime không có nghĩa giữ khóa cũ vô thời hạn hoặc bỏ qua kiểm soát an toàn. Hệ thống cần có khoảng thời gian hai phiên bản cùng tồn tại, tiêu chí chuyển đổi và điều kiện retire rõ ràng.

## 1. Bài toán và bối cảnh

Giả sử một dịch vụ quản lý hồ sơ khách hàng chạy trên nhiều instance Java trong production. Dữ liệu được mã hóa trước khi lưu vào database và object storage. Các instance gọi KMS để tạo hoặc giải mã Data Encryption Key (DEK); Key Encryption Key (KEK) được KMS/HSM bảo vệ.

Khóa KEK hiện tại là customer-kek-v1. Tổ chức cần chuyển sang customer-kek-v2 vì đến kỳ rotation theo cryptoperiod. Dịch vụ có các đặc điểm:

- Nhiều instance chạy đồng thời qua nhiều availability zone.
- Request đọc và ghi liên tục, không thể dừng toàn bộ dịch vụ để chuyển dữ liệu.
- Dữ liệu cũ có thể tồn tại nhiều năm do retention.
- Một số bản ghi có thể được cập nhật trong lúc migration chạy.
- Backup, archive và bản sao DR có thể còn tham chiếu khóa cũ.
- KMS có quota, latency và thời gian propagation policy cần tính đến.

Mục tiêu là chuyển writer sang K2, giữ reader tương thích với dữ liệu dùng K1 và chuyển đổi dữ liệu theo từng phần. K1 chỉ được thu hồi khi mọi phụ thuộc đã được xử lý hoặc có kế hoạch lưu trữ/khôi phục được phê duyệt.

## 2. Mục tiêu và điều kiện thành công

Thiết kế cần đáp ứng đồng thời:

1. Request đọc/ghi vẫn được phục vụ trong giai đoạn rotation theo SLO hiện tại.
2. Dữ liệu đã mã hóa bằng K1 vẫn đọc được trong thời gian chuyển tiếp.
3. Mọi dữ liệu mới sau cutover được bảo vệ bằng K2.
4. Metadata chỉ rõ key version của từng ciphertext hoặc encrypted DEK.
5. Migration không ghi đè dữ liệu mới hơn và có thể chạy lại an toàn.
6. Quyền truy cập K1/K2 được giới hạn theo principal và action.
7. Có thể theo dõi tiến độ, phát hiện lỗi và dừng/tiếp tục migration.
8. Không retire K1 trước khi backup, archive và workload còn phụ thuộc đã được xác minh.
9. Có phương án rollback tương thích với dữ liệu đã ghi bằng K2.

“Không downtime” cần được định nghĩa trong phạm vi vận hành: không có maintenance window buộc dừng toàn bộ dịch vụ, nhưng một request riêng lẻ vẫn có thể thất bại do lỗi mạng/KMS hoặc bị retry theo chính sách. Rotation cũng không bảo đảm không có độ trễ tăng nhẹ khi KMS bị tải cao.

## 3. Phân biệt loại rotation cần thực hiện

Trước khi thiết kế, phải xác định chính xác key nào được thay:

| Loại rotation | Thay đổi | Công việc dữ liệu |
|---|---|---|
| KEK rotation | Thay khóa dùng để wrap DEK | Thường có thể re-wrap encrypted DEK; ciphertext dữ liệu giữ nguyên nếu DEK vẫn tin cậy |
| DEK rotation | Thay khóa mã hóa dữ liệu | Cần re-encrypt dữ liệu bằng DEK mới |
| Signing key rotation | Thay private key dùng ký | Chuyển signer sang key mới; verifier phải biết public key/version cũ và mới |
| Credential rotation | Thay password, token hoặc credential gọi KMS | Cập nhật identity/secret và quyền; không tự động thay key material |

Case study này tập trung vào KEK rotation trong envelope encryption. Nếu DEK bị lộ, chỉ re-wrap DEK không đủ; phải tạo DEK mới và re-encrypt dữ liệu bị ảnh hưởng. Nếu K1 bị compromise, quy trình khẩn cấp có thể yêu cầu thu hẹp hoặc thu hồi quyền K1 nhanh hơn kế hoạch rotation thông thường.

## 4. Kiến trúc mục tiêu

Ứng dụng dùng logical key reference ổn định, còn key version được lưu cùng metadata của dữ liệu. KMS/HSM quản lý các KEK version và thực hiện thao tác wrap/unwrap hoặc re-encrypt theo khả năng dịch vụ.

~~~mermaid
flowchart LR
    A[Java service instances] --> B[Key resolver / KMS client]
    B --> C[KMS / HSM]
    C --> D[KEK v1]
    C --> E[KEK v2]
    A --> F[Data store]
    F --> G[Ciphertext + encrypted DEK + key version]
    H[Migration workers] --> B
    H --> F
    I[Audit / metrics] <-- A
    I <-- C
    I <-- H
~~~

Các thành phần:

- **Java service:** xử lý request đọc/ghi, không tự quản lý KEK plaintext.
- **Key resolver:** ánh xạ logical key reference và key version tới key resource cụ thể.
- **KMS/HSM:** giữ và sử dụng KEK theo policy; không trả KEK cho ứng dụng.
- **Data store:** lưu ciphertext, encrypted DEK, nonce/tag và metadata cần thiết.
- **Migration worker:** chuyển đổi encrypted DEK hoặc ciphertext theo batch.
- **Audit/metrics:** ghi thao tác key, tiến độ migration, lỗi và trạng thái retire.

Sơ đồ chỉ là kiến trúc khái niệm. Cách KMS biểu diễn key version, replica và thao tác ReEncrypt phụ thuộc nhà cung cấp.

## 5. Thiết kế metadata và key version

Mỗi bản ghi cần xác định key version chính xác. Không chỉ lưu một alias như customer-kek-current, vì alias có thể được trỏ sang version khác trong tương lai và làm mất khả năng xác định key đã bảo vệ bản ghi.

Metadata ví dụ:

~~~json
{
  "formatVersion": 3,
  "logicalKeyId": "customer-data",
  "kekKeyId": "customer-kek",
  "kekVersion": "v2",
  "encryptedDek": "base64-wrapped-dek",
  "cipherAlgorithm": "AES-256-GCM",
  "nonce": "base64-nonce",
  "ciphertext": "base64-ciphertext",
  "recordVersion": 184
}
~~~

Các trường phải được xác thực và ràng buộc với ciphertext bằng AEAD additional authenticated data (AAD) hoặc cơ chế integrity phù hợp. Metadata không được tin cậy nếu người dùng hoặc hệ thống lưu trữ có thể sửa key version mà không bị phát hiện.

Reader dùng logicalKeyId và kekVersion để tìm đúng key. Nếu version không tồn tại, ứng dụng phải báo lỗi có kiểm soát, phát cảnh báo và không thử mọi key một cách mù quáng. Không fallback sang K1 chỉ vì K2 không khả dụng nếu bản ghi đã khai báo K2; fallback như vậy có thể che giấu lỗi dữ liệu hoặc mở ra đường downgrade.

## 6. Quyền truy cập theo từng vai trò

Trong giai đoạn chuyển tiếp, quyền được cấp riêng cho runtime reader, writer, migration worker và key administrator:

| Principal | K1 | K2 | Ghi chú |
|---|---|---|---|
| Runtime reader | Decrypt/unwrap | Decrypt/unwrap | Chỉ đọc version ghi trong metadata |
| Runtime writer | Không cần Encrypt sau cutover | GenerateDataKey/Encrypt hoặc wrap | Chỉ tạo dữ liệu mới bằng K2 |
| Migration worker | Decrypt/unwrap | ReEncrypt/wrap | Quyền có thời hạn, giới hạn key và batch |
| Key administrator | Quản trị theo phê duyệt | Quản trị theo phê duyệt | Tách khỏi runtime principal |
| Backup/restore worker | Có thể cần đọc archive cũ | Đọc bản mới theo retention | Chỉ cấp khi thực sự cần |

Không cấp quyền quản trị key hoặc thay policy cho ứng dụng runtime. Migration worker nên có danh tính riêng, giới hạn trong key và môi trường cần di chuyển, có quota và audit. Sau khi migration hoàn tất, thu hồi quyền tạm thời của worker.

## 7. Giai đoạn 0: inventory và chuẩn bị

Trước khi thay đổi production:

- Liệt kê mọi dữ liệu có encrypted DEK được wrap bởi K1.
- Tìm backup, archive, snapshot, export, replica và bản sao DR.
- Xác định consumer đọc dữ liệu: API, batch, report, data pipeline và công cụ hỗ trợ.
- Kiểm tra version của ứng dụng, schema, thư viện crypto và KMS SDK.
- Đo baseline số request Decrypt/GenerateDataKey, latency, error rate và KMS quota.
- Xác minh K2 đã được tạo trong đúng account/project, region và HSM/KMS boundary.
- Kiểm tra backup/recovery của K2 và quyền truy cập trong DR.
- Xác định owner, change window, rollback criteria và người phê duyệt.

Inventory phải phân biệt dữ liệu active với dữ liệu archive. Bản ghi ít được đọc có thể không xuất hiện trong traffic hằng ngày nhưng vẫn cần K1 khi khôi phục sau nhiều tháng.

## 8. Giai đoạn 1: tạo K2 và kiểm thử trước

Tạo KEK mới bằng cơ chế được phê duyệt. Xác nhận:

- Thuật toán, key size, usage và purpose đúng policy.
- Key được tạo trong KMS/HSM mong muốn và có trạng thái enabled.
- Key policy cho phép đúng reader, writer và migration worker.
- Audit event ghi nhận tạo key và thay đổi policy.
- K2 có thể wrap/unwrap một DEK test.
- K2 có backup/recovery phù hợp và được kiểm chứng.

Không đưa K2 vào production writer chỉ vì thao tác tạo key thành công. Cần kiểm thử đầy đủ đường đi từ tạo encrypted DEK, lưu metadata, đọc lại và giải mã trong môi trường staging.

## 9. Giai đoạn 2: triển khai reader tương thích K1 và K2

Reader phải được nâng cấp trước khi writer chuyển sang K2. Trong giai đoạn này, writer vẫn dùng K1 để tránh tạo dữ liệu mà instance cũ chưa đọc được.

Triển khai theo rolling deployment:

1. Deploy phiên bản reader mới lên một nhóm instance.
2. Kiểm tra đọc bản ghi dùng K1.
3. Tạo dữ liệu K2 trong staging hoặc canary và xác minh reader mới đọc được.
4. Xác minh instance cũ chưa nhận dữ liệu K2 trong production.
5. Tiếp tục nâng cấp toàn bộ instance, batch worker và consumer.
6. Kiểm tra số instance còn chạy phiên bản reader cũ bằng deployment inventory.

Reader cần chọn key theo metadata. Không dùng logic “thử K2, nếu lỗi thì thử K1”. Nếu metadata chỉ K1 thì dùng K1; nếu chỉ K2 thì dùng K2. Lỗi authentication tag hoặc sai AAD phải được xử lý như lỗi integrity, không phải lý do đổi key.

## 10. Giai đoạn 3: cutover writer sang K2

Khi tất cả reader đã tương thích, chuyển active write key sang K2. Với nhiều instance, cần một cơ chế cutover có thể quan sát và nhất quán:

- Cấu hình activeWriteKeyVersion trong control store có version/revision.
- Writer chỉ nhận cấu hình đã được phê duyệt và kiểm tra key version.
- Mỗi record mới lưu chính xác version được dùng.
- Audit/metric ghi nhận write theo key version.
- Có thể rollout theo canary trước khi bật cho toàn bộ instance.

~~~mermaid
sequenceDiagram
    participant C as Config control
    participant W as Writer instances
    participant K as KMS
    participant D as Data store
    C->>W: activeWriteKeyVersion = v2
    W->>K: GenerateDataKey / wrap using K2
    K-->>W: Plaintext DEK + encrypted DEK
    W->>W: Encrypt payload with DEK
    W->>D: Save ciphertext + encrypted DEK + v2 metadata
    D-->>W: Commit success
~~~

Writer phải fail safely nếu K2 không khả dụng. Không tự động quay về K1 chỉ để giữ write availability nếu chính sách đã yêu cầu K2. Tùy nghiệp vụ, request có thể được retry, đưa vào queue hoặc trả lỗi tạm thời; không ghi ciphertext bằng version khác với metadata đã công bố.

Sau cutover, theo dõi writes_by_key_version. Nếu còn write K1, tìm instance cũ, batch job, consumer hoặc đường code chưa được cập nhật trước khi bắt đầu retire.

## 11. Giai đoạn 4: re-wrap encrypted DEK

Vì case study chỉ thay KEK và giả định DEK chưa bị compromise, dữ liệu nghiệp vụ không cần mã hóa lại. Migration worker chỉ chuyển encrypted DEK từ K1 sang K2:

1. Đọc bản ghi và encrypted DEK version K1.
2. Gọi KMS/HSM để re-wrap DEK từ K1 sang K2, ưu tiên thao tác server-side nếu dịch vụ hỗ trợ.
3. Nhận encrypted DEK mới.
4. Cập nhật encrypted DEK và kekVersion=v2 cùng transaction/conditional update.
5. Giữ nguyên ciphertext, nonce, tag và AAD của dữ liệu nếu chúng không phụ thuộc metadata đã thay đổi; nếu AAD có chứa key version thì phải cập nhật/re-encrypt theo thiết kế.
6. Đánh dấu bản ghi hoàn tất sau khi commit thành công.

~~~mermaid
flowchart LR
    A[Ciphertext dữ liệu] --> D[Giữ nguyên]
    B[Encrypted DEK K1] --> C[KMS re-wrap K1 sang K2]
    C --> E[Encrypted DEK K2]
    D --> F[Record mới sau migration]
    E --> F
~~~

Re-wrap không cần trả plaintext DEK về ứng dụng nếu KMS hỗ trợ ReEncrypt hoặc thao tác tương đương. Nếu ứng dụng phải unwrap rồi wrap lại, plaintext DEK sẽ đi qua bộ nhớ của migration worker; cần giới hạn quyền, không log, giảm thời gian tồn tại và xóa tham chiếu sau khi sử dụng.

Nếu AAD của ciphertext ràng buộc với encrypted DEK hoặc key version, phải tuân theo thiết kế AAD. Không được giữ nguyên ciphertext khi thay metadata làm thay đổi AAD được xác thực.

## 12. Khi nào phải re-encrypt dữ liệu?

Re-wrap chỉ thay lớp bảo vệ DEK. Nếu DEK bị lộ, attacker đã có thể giải mã ciphertext bằng DEK cũ, bất kể encrypted DEK được wrap bằng K2. Khi đó cần:

1. Tạo DEK mới.
2. Giải mã dữ liệu bằng DEK cũ trong môi trường kiểm soát.
3. Mã hóa lại bằng DEK mới và nonce mới.
4. Wrap DEK mới bằng K2.
5. Cập nhật ciphertext, encrypted DEK và metadata nguyên tử.
6. Thu hồi DEK cũ theo cơ chế lưu trữ/quản lý phù hợp.

| Tình huống | Phương án |
|---|---|
| Rotation KEK định kỳ, DEK vẫn an toàn | Re-wrap encrypted DEK |
| KEK K1 bị nghi ngờ lộ | Đánh giá khả năng plaintext DEK bị lấy; re-wrap và có thể re-encrypt theo phạm vi rủi ro |
| DEK bị lộ | Tạo DEK mới và re-encrypt dữ liệu |
| Chỉ đổi alias | Xác định key material có thực sự đổi không; đổi alias đơn thuần không phải cryptographic rotation |

Quyết định re-encrypt cần tính đến dung lượng dữ liệu, thời gian, KMS quota, tải CPU, transaction và tác động tới latency. Nếu compromise được xác nhận, ưu tiên bảo mật có thể yêu cầu chấp nhận gián đoạn hoặc hạn chế truy cập thay vì giữ cửa sổ dual-read dài.

## 13. Migration chạy song song và xử lý cập nhật đồng thời

Migration thường chạy nền theo batch trong khi ứng dụng vẫn phục vụ request. Rủi ro chính là một bản ghi thay đổi sau khi worker đọc nhưng trước khi worker ghi kết quả. Nếu worker cập nhật không có điều kiện, ciphertext hoặc metadata mới có thể bị ghi đè.

Dùng optimistic locking:

~~~text
record = read(recordId)
if record.kekVersion == "v1":
    wrappedDekV2 = kms.rewrap(record.encryptedDek, K1, K2)
    update record
       set encryptedDek = wrappedDekV2,
           kekVersion = "v2",
           recordVersion = recordVersion + 1
     where id = record.id
       and kekVersion = "v1"
       and recordVersion = record.recordVersion
    if update_count == 0:
        discard result and retry from latest record
~~~

Worker phải idempotent: nếu chạy lại sau khi process chết, bản ghi đã ở K2 được bỏ qua; bản ghi còn K1 có thể được xử lý lại. Dùng checkpoint bền vững, retry có backoff, dead-letter queue và giới hạn concurrency. Không tăng concurrency vượt quota KMS/HSM hoặc làm ảnh hưởng request online.

Nếu dữ liệu thay đổi cấu trúc trong lúc rotation, migration cần tương thích với schema version cũ và mới. Có thể cần expand-migrate-contract: mở rộng schema trước, chuyển đổi dữ liệu, rồi mới loại bỏ trường cũ.

## 14. Kiểm soát tải và ảnh hưởng tới SLO

Rotation có thể tạo ra nhiều request KMS bổ sung. Migration worker cần được điều tiết:

- Chạy theo batch nhỏ và có giới hạn tốc độ.
- Đặt concurrency tối đa theo quota, latency và capacity KMS/HSM.
- Dùng exponential backoff có jitter cho throttling và lỗi tạm thời.
- Ưu tiên traffic online so với background migration.
- Dừng hoặc giảm tốc khi error rate/latency vượt ngưỡng.
- Có thể tạm dừng và tiếp tục từ checkpoint mà không làm sai trạng thái.
- Theo dõi chi phí API, CPU, I/O và database lock contention.

Các chỉ số nên theo dõi:

| Metric | Mục đích |
|---|---|
| writes_by_key_version | Xác nhận writer đã chuyển hoàn toàn sang K2 |
| decrypts_by_key_version | Theo dõi phụ thuộc đọc K1/K2 |
| records_pending_rotation | Số bản ghi còn encrypted DEK K1 |
| rewrap_success_total | Số bản ghi chuyển đổi thành công |
| rewrap_failure_total | Lỗi migration |
| rewrap_retry_total | Số lần retry |
| kms_latency / kms_throttle_total | Ảnh hưởng tới KMS |
| old_key_access_after_cutover | Phát hiện consumer cũ hoặc hành vi bất thường |
| decrypt_error_rate | Phát hiện metadata/key mismatch hoặc lỗi integrity |

Không chỉ nhìn phần trăm migration hoàn tất. Cần biết chính xác dữ liệu nào còn phụ thuộc K1, ở đâu và vì sao.

## 15. Rollback không làm mất dữ liệu đã ghi bằng K2

Rollback phải được thiết kế trước cutover. Trong giai đoạn chuyển đổi, reader mới đọc được cả K1 và K2. Nếu cần rollback ứng dụng, phiên bản rollback vẫn phải giữ khả năng đọc K2 hoặc phải có một bước chuyển đổi dữ liệu rõ ràng.

Các nguyên tắc:

- Không rollback về reader chỉ hỗ trợ K1 sau khi writer đã ghi dữ liệu K2.
- Không xóa K2 nếu đã có record hoặc backup phụ thuộc K2.
- Có thể tạm dừng migration và giữ cả K1/K2 hoạt động nếu lỗi không liên quan compromise.
- Nếu cần quay writer về K1, chỉ thực hiện khi K1 còn được xem là an toàn và đã có phê duyệt.
- Không tự động re-wrap ngược chỉ để khớp code cũ; kiểm tra metadata và AAD trước.
- Lưu config revision để biết chính xác thời điểm cutover.

Nếu K1 bị compromise, rollback không được mở lại quyền K1 chỉ vì ứng dụng mới gặp lỗi. Khi đó phải sửa reader/writer hoặc chuyển sang key thay thế khác; có thể chấp nhận giảm availability theo incident policy.

## 16. Điều kiện retire K1

Không retire K1 dựa duy nhất vào trạng thái migration worker. Cần xác minh:

- Không còn record active tham chiếu encrypted DEK K1.
- Không còn write mới bằng K1 sau cutover.
- Không có decrypt request K1 từ runtime trong khoảng thời gian bao phủ batch và workload ít chạy.
- Backup, archive, snapshot, export và DR copy đã được re-wrap, hết retention hoặc có recovery plan được phê duyệt.
- Mọi consumer, job và công cụ hỗ trợ đều đã chuyển đổi.
- Restore drill thành công với dữ liệu đã chuyển sang K2.
- Audit log và inventory xác nhận key usage.
- Owner và approver chấp nhận retire.

Sau khi đủ điều kiện:

1. Thu hồi quyền Decrypt/Unwrap K1 khỏi runtime và migration worker.
2. Theo dõi deny event để phát hiện phụ thuộc bị bỏ sót.
3. Disable K1 theo quy trình.
4. Giữ trong thời gian chờ nếu policy/retention yêu cầu.
5. Destroy K1 theo approval và quy trình key destruction.

Nếu archive cần K1 trong thời gian dài, có thể giữ key ở trạng thái decrypt-only với quyền, network và audit nghiêm ngặt. Đây là ngoại lệ có thời hạn/owner rõ ràng, không phải lý do để giữ quyền runtime rộng.

## 17. Audit và phân tách trách nhiệm

Mỗi giai đoạn cần tạo bằng chứng:

- Ai tạo K2, ai thay policy và ai phê duyệt.
- Khi nào reader rollout hoàn tất và writer cutover xảy ra.
- Key version nào được dùng cho từng thao tác.
- Migration worker đã xử lý bao nhiêu record, bao nhiêu lỗi và checkpoint nào.
- Ai thay đổi quyền K1, disable hoặc destroy.
- Kết quả restore drill và kiểm tra dữ liệu còn tồn.

Không ghi plaintext DEK, KEK, private key, password hoặc token vào log. Audit nên ghi key ID/version, principal, action, request ID, result, timestamp và correlation ID.

Tách vai trò runtime, migration và key administration. Người chạy migration không mặc nhiên có quyền thay policy hoặc destroy key. Các thao tác không thể đảo ngược cần phê duyệt theo quy trình tổ chức.

## 18. Kế hoạch kiểm thử trước production

| Nhóm test | Kịch bản | Kết quả mong đợi |
|---|---|---|
| Compatibility | Reader cũ và mới đọc record K1 | Không lỗi trước cutover |
| New version | Reader mới đọc record K2 | Đọc đúng plaintext |
| Metadata integrity | Sửa keyVersion/AAD | Bị từ chối |
| Writer cutover | Nhiều instance chuyển sang K2 | Không còn write K1 sau khi rollout hoàn tất |
| Permission | Runtime chỉ có quyền theo role | Không có quyền quản trị key |
| Re-wrap | Chuyển encrypted DEK K1 sang K2 | Ciphertext dữ liệu vẫn đọc được |
| Concurrency | Record được cập nhật trong lúc migration | Optimistic lock ngăn ghi đè |
| Idempotency | Worker chạy lại sau crash | Record K2 không bị xử lý sai |
| Throttling | KMS trả throttling/timeout | Retry có backoff, online SLO được bảo vệ |
| Rollback | Ứng dụng rollback sau khi có record K2 | Reader vẫn đọc được K2 |
| Backup/restore | Khôi phục dữ liệu sau rotation | Đọc được dữ liệu theo retention |
| Retirement | Thu hồi K1 khi đã chuyển đổi | Request phụ thuộc bị phát hiện và từ chối |

Thực hiện rehearsal trên staging với dữ liệu đại diện, sau đó chạy canary production có giới hạn. Không thử disable hoặc destroy K1 production trong test thông thường.

## 19. Runbook triển khai tham khảo

Một runbook thực tế có thể tổ chức như sau:

| Giai đoạn | Hành động | Gate để đi tiếp |
|---|---|---|
| Prepare | Inventory, tạo K2, kiểm tra policy/backup | K2 hoạt động và recovery được xác minh |
| Reader rollout | Deploy dual-read trên mọi consumer | Không còn reader chỉ hỗ trợ K1 |
| Writer cutover | Chuyển active write version sang K2 | Metric xác nhận mọi write dùng K2 |
| Data migration | Re-wrap DEK theo batch | Pending records giảm về 0 hoặc có exception được duyệt |
| Validation | Kiểm tra backup, restore, audit và decrypt K1 usage | Không còn dependency không giải thích được |
| Retire | Thu hồi quyền, disable, chờ và destroy K1 | Approval và retention gate đã đạt |

Ở mỗi gate cần có người chịu trách nhiệm, bằng chứng, điều kiện dừng và cách quay lại trạng thái an toàn. Nếu metric không đáng tin cậy hoặc inventory chưa đầy đủ, không chuyển sang bước retire.

## 20. Rủi ro và lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chuyển writer trước khi mọi reader hỗ trợ K2 | Instance cũ không đọc được record mới | Reader-first rollout và kiểm kê consumer |
| Chỉ lưu alias, không lưu key version | Không xác định được key đã bảo vệ record | Lưu keyId/version cùng ciphertext và xác thực metadata |
| Fallback sang K1 khi K2 lỗi | Che giấu lỗi và tạo dữ liệu bằng key cũ ngoài ý muốn | Chọn key theo metadata; writer fail safe |
| Re-wrap khi DEK đã bị lộ | Ciphertext vẫn có thể bị giải mã bằng DEK cũ | Tạo DEK mới và re-encrypt |
| Migration không có optimistic locking | Ghi đè dữ liệu mới hơn | Conditional update theo record version |
| Migration không idempotent | Retry có thể làm hỏng hoặc lặp side effect | Checkpoint, event ID và kiểm tra version trước khi xử lý |
| Destroy K1 khi backup còn phụ thuộc | Không thể restore dữ liệu lịch sử | Kiểm tra retention và restore drill |
| Cấp quyền admin cho migration worker | Tăng phạm vi thiệt hại nếu worker bị xâm nhập | Tách quyền và giới hạn action/resource |
| Không theo dõi K1 usage sau cutover | Bỏ sót consumer hoặc truy cập bất thường | Audit/metric theo key version và principal |
| Rollback về code chỉ đọc K1 | Không đọc được dữ liệu K2 | Giữ reader tương thích ngược trong các bản rollback |

## 21. Checklist hoàn tất rotation không downtime

- [ ] Xác định loại rotation: KEK, DEK, signing key hay credential.
- [ ] Inventory dữ liệu active, archive, backup, snapshot, replica và consumer.
- [ ] Tạo K2, xác minh algorithm, policy, region và recovery.
- [ ] Lưu keyId/keyVersion và metadata integrity-protected cùng dữ liệu.
- [ ] Deploy reader hỗ trợ K1/K2 tới mọi instance và consumer.
- [ ] Kiểm thử positive/negative cho cả hai version.
- [ ] Chuyển writer sang K2 bằng config revision/canary có thể quan sát.
- [ ] Xác nhận không còn write K1 sau cutover.
- [ ] Chọn re-wrap DEK hay re-encrypt dựa trên trạng thái tin cậy của DEK.
- [ ] Migration dùng optimistic locking, idempotency, checkpoint và rate limit.
- [ ] Theo dõi latency, KMS quota, lỗi, retry và số record còn K1.
- [ ] Xác minh backup/restore và dữ liệu ít được truy cập.
- [ ] Thu hồi quyền K1 theo principal/action và quan sát deny event.
- [ ] Disable/destroy K1 chỉ sau khi đạt retention và approval gate.
- [ ] Lưu audit evidence, runbook, owner và kết quả rehearsal.

Key rotation không downtime là một quá trình chuyển đổi có kiểm soát giữa hai phiên bản khóa. Thiết kế đáng tin cậy cần reader tương thích trước, writer chuyển sang key mới, dữ liệu được migration an toàn, quyền cũ được thu hồi sau khi xác minh và khóa chỉ được destroy khi mọi phụ thuộc, bao gồm backup và archive, đã được giải quyết.
