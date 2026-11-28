# Key rotated event

Trong chương **Audit và monitoring** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích sự kiện key rotation (key rotated event), dữ liệu cần ghi nhận và cách giám sát sau khi khóa được xoay vòng. Rotation có thể diễn ra tự động theo lịch, do operator yêu cầu hoặc để ứng phó sự cố. Một sự kiện rotation đáng tin cậy giúp xác nhận phiên bản khóa nào đã có hiệu lực, ai hoặc hệ thống nào khởi tạo, rotation có thành công không và workload đã chuyển sang sử dụng phiên bản mới hay chưa.

## 1. Key rotated event là gì?

**Key rotated event** là bản ghi hoặc thông điệp audit cho biết một cryptographic key đã trải qua một lần rotation thành công, hoặc một phiên bản key mới đã được tạo và đưa vào trạng thái sử dụng theo semantics của hệ thống quản lý khóa.

Event này thường được phát ra bởi KMS, HSM, key management service hoặc một control plane quản lý vòng đời khóa. Nó có thể được chuyển tới audit log, event bus, SIEM, hệ thống monitoring hoặc workflow tự động để các thành phần phụ thuộc biết cần cập nhật.

Một key rotated event hữu ích cần trả lời:

- Key nào đã được rotation?
- Phiên bản cũ và phiên bản mới được định danh ra sao?
- Rotation hoàn tất vào thời điểm nào?
- Ai hoặc thành phần nào khởi tạo?
- Trigger là lịch tự động, thao tác thủ công, policy hay incident?
- Thuật toán, key type và purpose có thay đổi không?
- Key version mới đã active chưa?
- Các consumer cần hành động gì tiếp theo?
- Event có thể được xác minh là đến từ nguồn tin cậy hay không?

Event không chứa key material, private key, secret bytes, password hoặc plaintext. Nó chỉ mang metadata cần thiết để audit và điều phối vòng đời.

## 2. Phân biệt rotation event với các sự kiện liên quan

Một quy trình rotation thường tạo ra nhiều sự kiện. Không nên coi mọi sự kiện có chữ “rotation” là bằng chứng key mới đã được sử dụng.

| Event hoặc trạng thái | Ý nghĩa | Có chứng minh rotation hoàn tất không? |
|---|---|---|
| Rotation scheduled | Lịch rotation đã được cấu hình | Không |
| Rotation enabled | Chính sách tự động rotation đã được bật | Không |
| Rotation requested/started | Có yêu cầu hoặc tiến trình rotation đã bắt đầu | Không |
| Key version created | Một phiên bản key mới đã được tạo | Chưa chắc; cần biết version đã active chưa |
| Key rotated | Rotation hoàn tất theo semantics của KMS/HSM | Có, trong phạm vi được định nghĩa |
| Rotation failed | Tiến trình rotation thất bại | Không |
| Key version activated | Version mới được chọn cho operation mới | Có thể là bước hoàn tất tùy nền tảng |
| Old version disabled/retired | Phiên bản cũ bị ngừng sử dụng theo policy | Không tự chứng minh mọi consumer đã chuyển |
| Old key destroyed | Key material cũ đã bị hủy theo quy trình | Không phải rotation event; đây là sự kiện destruction riêng |

Một số nền tảng phát một event duy nhất khi rotation hoàn tất; nền tảng khác phát nhiều event theo từng bước. Khi chuẩn hóa, cần giữ nguyên event type gốc và ánh xạ rõ trạng thái nội bộ, tránh đổi một sự kiện rotation.started thành key.rotated.

## 3. Vì sao cần audit key rotation?

Rotation làm thay đổi trạng thái hoặc phiên bản của tài sản mật mã. Nếu không ghi nhận và giám sát, tổ chức khó chứng minh khóa được xoay đúng lịch, khó phát hiện thao tác trái phép và khó xác định nguyên nhân khi ứng dụng không còn giải mã được dữ liệu.

Audit key rotation hỗ trợ:

- Chứng minh key được xoay vòng theo cryptoperiod và policy.
- Phát hiện rotation thủ công ngoài change window hoặc không có approval.
- Theo dõi key version mới đã được tạo và kích hoạt.
- Phát hiện rotation thất bại, bị trì hoãn hoặc không có event xác nhận.
- Xác định workload nào vẫn sử dụng version cũ.
- Điều tra key compromise hoặc thay đổi bất thường.
- Đối chiếu KMS/HSM audit với deployment, incident và change management.
- Chứng minh kiểm soát trong audit nội bộ hoặc đánh giá tuân thủ.

Rotation event là một phần của audit trail. Nó không thay thế inventory, key policy, change record, application telemetry hoặc bằng chứng xác minh dữ liệu sau rotation.

## 4. Các loại rotation và semantics của event

Ý nghĩa của key.rotated phụ thuộc loại khóa và mô hình quản lý:

| Loại rotation | Điều thay đổi | Điều event cần mô tả |
|---|---|---|
| Automatic symmetric key rotation | KMS tạo key material version mới dưới logical key hiện có | Logical key ID, version mới, trigger tự động và thời điểm hiệu lực |
| Manual key replacement | Tạo key resource mới rồi chuyển alias hoặc cấu hình sang key mới | Old/new key ID, cutover, alias mapping và consumer |
| KEK rotation | Thay key dùng để wrap DEK | KEK version mới và trạng thái rewrap của wrapped DEK |
| DEK rotation | Tạo DEK mới cho dữ liệu hoặc phạm vi dữ liệu | DEK version, data scope và tình trạng re-encryption |
| HMAC/signing key rotation | Thay secret hoặc signing key pair | Key ID/version mới, consumer cập nhật và thời gian overlap |
| TLS certificate/key rotation | Thay key pair, certificate hoặc cả hai | Key version, certificate serial/fingerprint và endpoint rollout |
| CA key rollover | Thay key của CA và có thể thay trust chain | Ceremony, issuer, trust anchor transition và phạm vi chứng thư |

Trong một số KMS, logical key ID giữ nguyên qua các lần rotation và dịch vụ tự chọn key material version phù hợp khi decrypt ciphertext cũ. Ở hệ thống khác, rotation tạo resource mới và ứng dụng phải cập nhật key ID hoặc alias. Vì vậy event schema cần phân biệt logical_key_id, key_resource_id và key_version_id khi nền tảng có các khái niệm đó.

## 5. Rotation không đồng nghĩa re-encryption hoặc destruction

Rotation thường làm cho operation mới dùng key version mới. Điều đó không có nghĩa mọi dữ liệu đã mã hóa trước đây đã được mã hóa lại.

- Với một số KMS, ciphertext cũ tiếp tục được giải mã bằng key material version cũ được lưu trong cùng logical key.
- Với envelope encryption, rotation KEK có thể chỉ cần rewrap DEK; ciphertext dữ liệu không nhất thiết phải thay đổi.
- Rotation DEK có thể yêu cầu mã hóa lại dữ liệu hoặc tạo object version mới.
- Rotation signing key yêu cầu consumer nhận public key hoặc secret version mới; chữ ký cũ vẫn cần được xác minh theo policy.
- Key version cũ có thể cần giữ lại để giải mã hoặc xác minh dữ liệu lịch sử.

Do đó, event key.rotated phải ghi đúng phạm vi hoàn tất. Nếu chỉ có key material mới được tạo, không nên tuyên bố dữ liệu đã re-encrypt. Nếu chỉ KEK được rotate, không nên mô tả DEK hoặc ciphertext đã thay đổi.

Rotation, retirement, revocation, disable và destruction là các trạng thái/sự kiện khác nhau. Hủy key cũ quá sớm có thể khiến dữ liệu lịch sử không thể giải mã; giữ key cũ hoạt động vô thời hạn lại làm tăng bề mặt tấn công.

## 6. Vòng đời sự kiện rotation

Một quy trình tổng quát có thể có các giai đoạn:

1. **Scheduled:** policy xác định thời điểm hoặc điều kiện rotation.
2. **Requested:** operator, automation hoặc incident workflow yêu cầu rotation.
3. **Started:** KMS/HSM bắt đầu thao tác.
4. **Created:** key material/version mới được tạo hoặc nhập theo policy.
5. **Activated:** version mới được chọn cho operation mới.
6. **Published:** hệ thống phát event xác nhận rotation.
7. **Consumer migration:** ứng dụng, service hoặc đối tác cập nhật tham chiếu.
8. **Verified:** kiểm tra sign/verify, encrypt/decrypt hoặc unwrap với version mới.
9. **Old version retired:** version cũ bị hạn chế hoặc chuyển sang decrypt-only/verify-only nếu cần.
10. **Destroyed:** key material cũ bị hủy khi hết dependency và retention.

Không phải sản phẩm nào cũng phát event riêng cho mọi giai đoạn. Hệ thống giám sát nên phân biệt trạng thái nguồn thực sự cung cấp với trạng thái suy ra từ quy trình nội bộ.

~~~mermaid
flowchart TD
    A[Rotation policy hoặc request] --> B[Rotation started]
    B --> C[New key version created]
    C --> D[New version activated]
    D --> E[Key rotated event published]
    E --> F[Consumer migration]
    F --> G[Verify new version]
    G --> H[Old version retired]
    H --> I[Retention/dependency check]
    I --> J[Old material destroyed khi đủ điều kiện]
~~~

Nếu rotation thất bại ở bất kỳ bước nào, phát event failure riêng, giữ trạng thái key rõ ràng và kích hoạt quy trình xử lý. Không phát key.rotated thành công chỉ vì request đã được chấp nhận.

## 7. Các trường dữ liệu nên có trong key rotated event

Event nên dùng schema có phiên bản và chứa đủ metadata để điều tra, liên kết và xử lý tự động:

| Trường | Mục đích | Ví dụ |
|---|---|---|
| event_id | Định danh duy nhất của event | UUID |
| event_type | Loại sự kiện chuẩn hóa | key.rotated |
| event_version | Phiên bản schema | 1 |
| occurred_at | Thời điểm rotation xảy ra tại nguồn | UTC timestamp |
| published_at | Thời điểm event được phát đi | UTC timestamp |
| source | Hệ thống phát event | kms-prod-a |
| actor | Principal hoặc service khởi tạo | rotation-scheduler |
| request_id | ID request phía KMS/HSM | request reference |
| correlation_id | Liên kết với incident/change/workflow | CHG-20481 |
| logical_key_id | Định danh logic của key | orders-kek |
| key_resource_id | ID resource của KMS/HSM | resource reference |
| old_version_id | Version cũ | version-17 |
| new_version_id | Version mới | version-18 |
| rotation_trigger | Lý do/trigger | scheduled, manual, compromise |
| status | Kết quả | succeeded |
| effective_at | Thời điểm version mới có hiệu lực | UTC timestamp |
| algorithm/key_type | Thuật toán và loại key | AES-256, symmetric |
| purpose | Mục đích của key | envelope-kek |
| environment/region | Phạm vi triển khai | production / region-a |
| approval_ref | Tham chiếu phê duyệt nếu có | approval ID |

Không phải mọi nguồn đều cung cấp old/new version ID hoặc effective time. Schema chuẩn hóa cần cho phép trường tùy chọn, ghi rõ trường nào là nguồn cung cấp và trường nào do hệ thống nội bộ suy ra. Không bịa version ID nếu KMS không công khai chúng.

Các trường metadata nhạy cảm như principal, key ID và context vẫn cần phân quyền đọc, dù chúng không phải key material. Không đưa raw key, private key, secret, password, plaintext hoặc wrapped key bytes vào event.

## 8. Ví dụ normalized event

Ví dụ JSON dưới đây minh họa một event đã chuẩn hóa cho lần rotation KEK thành công:

~~~json
{
  "event_id": "8f2c2f7d-9b15-4db8-8f1a-0f3c5f9e2a10",
  "event_type": "key.rotated",
  "event_version": 1,
  "occurred_at": "2026-11-28T03:15:22Z",
  "published_at": "2026-11-28T03:15:23Z",
  "source": "kms-prod-a",
  "actor": {
    "type": "service",
    "id": "rotation-scheduler"
  },
  "request_id": "req-7c1a",
  "correlation_id": "CHG-20481",
  "key": {
    "logical_key_id": "orders-kek-prod",
    "resource_id": "key-resource-91",
    "old_version_id": "version-17",
    "new_version_id": "version-18",
    "algorithm": "AES-256",
    "purpose": "envelope-kek"
  },
  "rotation": {
    "trigger": "scheduled",
    "status": "succeeded",
    "effective_at": "2026-11-28T03:15:22Z"
  },
  "scope": {
    "environment": "production",
    "region": "region-a"
  },
  "approval_ref": "approval-381"
}
~~~

Giá trị trong ví dụ là dữ liệu giả định để minh họa schema. Event production phải lấy từ nguồn audit thật, giữ nguyên timestamp và ID của nguồn, đồng thời ghi rõ mapping nếu hệ thống chuẩn hóa đổi tên trường.

## 9. Event source và độ tin cậy của bằng chứng

Nguồn phát event có thể là:

- KMS audit log hoặc native event stream.
- HSM audit log hoặc security appliance.
- Key management controller nội bộ.
- Rotation orchestrator.
- Certificate lifecycle manager.
- Secret manager hoặc signing service.

Ưu tiên event do hệ thống thực hiện rotation phát ra, hoặc audit record được ký/xác thực bởi control plane. Event do ứng dụng tự gửi rằng “đã rotate” không đủ làm bằng chứng độc lập nếu ứng dụng cũng là thành phần có thể bị xâm phạm.

Khi kết hợp nhiều nguồn:

1. Giữ raw event gốc ở vùng audit có kiểm soát.
2. Chuẩn hóa thành schema chung cho SIEM/event bus.
3. Ghi nguồn, thời gian nhận và mapping version.
4. Liên kết bằng request ID, key ID và correlation ID.
5. Không thay đổi raw evidence khi enrich metadata.

Event bus và pipeline phải xác thực producer, mã hóa khi truyền, giới hạn quyền publish/subscribe và bảo vệ khỏi sửa đổi trái phép. Consumer không được tin một message chỉ vì nó có event_type key.rotated; cần xác minh nguồn và integrity theo nền tảng.

## 10. Audit event, notification và state change

Ba loại dữ liệu này phục vụ mục đích khác nhau:

- **Audit event:** bằng chứng một hành động đã xảy ra, ai thực hiện và kết quả.
- **Notification:** thông báo để người hoặc hệ thống hành động, có thể được retry hoặc gửi nhiều lần.
- **Current state:** trạng thái hiện tại của key trong KMS/inventory.

Một notification có thể bị trễ hoặc lặp; current state có thể đã thay đổi sau khi event được phát. Audit event là bằng chứng lịch sử và cần được lưu theo retention policy. Không dùng notification thay thế audit log, cũng không suy luận current state chỉ từ một message cũ.

Ví dụ, consumer nhận event key.rotated nhưng key sau đó đã bị disable do incident. Trước khi hành động, consumer cần truy vấn trạng thái hiện tại hoặc xác minh event sequence phù hợp, không tự động kích hoạt key chỉ dựa vào notification.

## 11. Ghi audit và bảo toàn tính toàn vẹn

Audit log cần cho phép dựng lại chuỗi hành động và chứng minh dữ liệu không bị sửa tùy tiện:

- Ghi append-only hoặc lưu trong hệ thống có cơ chế chống sửa đổi.
- Đồng bộ thời gian và giữ timestamp UTC cùng nguồn thời gian.
- Hạn chế quyền ghi, xóa và thay đổi retention.
- Tách quyền quản trị key khỏi quyền quản trị audit log.
- Bảo vệ log bằng mã hóa và kiểm soát truy cập.
- Dùng hash chaining, digital signature hoặc cơ chế tamper-evident nếu yêu cầu bảo đảm cao.
- Gửi bản sao tới miền quản trị độc lập để giảm nguy cơ attacker xóa dấu vết cùng hệ thống nguồn.
- Theo dõi tình trạng mất log, trễ ingest và khoảng trống sequence nếu nguồn hỗ trợ.

Không phải event pipeline nào cũng cần tự triển khai hash chain. Có thể dùng dịch vụ audit có integrity control đã được đánh giá. Điều quan trọng là xác định threat model, retention, quyền quản trị và cách phát hiện log bị thiếu hoặc bị thay đổi.

## 12. Event delivery: duplicate, delay và ordering

Event bus thường có thể giao message theo mô hình at-least-once; consumer có thể nhận cùng event nhiều lần. Một số hệ thống cũng có thể giao trễ hoặc không bảo đảm thứ tự toàn cục.

Consumer cần:

- Dùng event_id để deduplicate.
- Xử lý idempotent: nhận lại event không tạo thêm rotation hoặc thay đổi trạng thái sai.
- Kiểm tra occurred_at, published_at và source sequence nếu có.
- Không giả định thứ tự đến chính là thứ tự xảy ra.
- Đưa event không hợp lệ hoặc không thể xử lý vào dead-letter queue theo policy.
- Retry có backoff và giới hạn, không retry vô hạn gây bão tải.
- Theo dõi event bị mất, trễ hoặc không được acknowledge.

Nếu event version 19 đến trước version 18, consumer cần dựa vào version sequence hoặc truy vấn current state để xử lý. Không hạ trạng thái key về version cũ chỉ vì một event cũ đến trễ.

## 13. Monitoring sau rotation

Một rotation thành công tại KMS chưa đảm bảo tất cả ứng dụng đã chuyển đổi. Monitoring cần theo dõi cả key service và consumer.

Các chỉ số và tín hiệu hữu ích:

- Số rotation thành công/thất bại theo key, purpose và môi trường.
- Thời gian từ request đến activation và từ activation đến event publication.
- Số key quá hạn rotation hoặc chưa có event xác nhận theo lịch.
- Số workload còn gọi key version cũ.
- Tỷ lệ decrypt/unwrap thất bại sau cutover.
- Số signature verification failure sau signing key rotation.
- Số endpoint còn trình bày certificate/key version cũ.
- Số consumer chưa acknowledge event.
- Số event trễ, duplicate, bị reject hoặc vào dead-letter queue.
- Số operation trên key cũ sau thời điểm retirement dự kiến.

Monitoring phải có baseline. Một rotation mỗi quý ở một nhóm key có thể bình thường; cùng một key bị rotate nhiều lần trong vài phút có thể là dấu hiệu automation lỗi hoặc hành vi trái phép.

## 14. Cảnh báo cần thiết

Alert nên gắn với tác động và hành động xử lý:

| Điều kiện | Mức độ gợi ý | Hành động |
|---|---|---|
| Rotation thất bại cho key production quan trọng | High/Critical tùy dependency | Kiểm tra KMS/HSM, quota, policy và trạng thái version |
| Rotation thủ công ngoài change window | High | Xác minh actor, approval và incident |
| Rotation bởi principal không được phép | Critical | Cô lập quyền, điều tra credential và key state |
| Không có rotation event sau lịch dự kiến | Medium/High | Kiểm tra scheduler, event source và key inventory |
| Event không có old/new version hoặc request ID bắt buộc | Medium | Kiểm tra schema/source mapping |
| Consumer chưa cập nhật sau cutover | High nếu ảnh hưởng service | Liên hệ owner, kiểm tra rollout và dependency |
| Decrypt/sign failure tăng sau rotation | High | Kiểm tra key mapping, provider, version và data migration |
| Key cũ vẫn được dùng sau retirement | High | Xác định consumer còn sót, đánh giá có cần block |
| Event trễ hoặc mất trong pipeline | Medium/High | Kiểm tra ingest, queue, subscription và audit source |
| Rotation xảy ra quá dày bất thường | High | Kiểm tra automation loop hoặc hành vi trái phép |

Không tạo alert cho mọi event thành một incident. Có thể dùng dashboard và log cho event thông thường, còn alert chỉ phát khi có điều kiện bất thường hoặc vi phạm policy. Mỗi alert cần owner, severity, runbook và tiêu chí đóng.

## 15. Correlation với change, incident và key inventory

Key rotated event nên liên kết với các hệ thống khác:

- **Change management:** change ID, người phê duyệt, cửa sổ triển khai và kế hoạch rollback.
- **Incident management:** incident ID khi rotation do compromise hoặc emergency response.
- **Key inventory:** owner, purpose, cryptoperiod, dependency và trạng thái version.
- **Deployment pipeline:** release ID, workload rollout và phiên bản cấu hình.
- **KMS/HSM audit:** request ID, actor, operation và key state.
- **Application telemetry:** key ID/version được consumer sử dụng thực tế.

Correlation ID giúp trả lời một chuỗi câu hỏi: rotation được yêu cầu bởi ai, KMS đã tạo version nào, event được phát khi nào, ứng dụng nào nhận event, consumer nào chuyển đổi thành công và version cũ còn được gọi ở đâu.

Không đưa nội dung bí mật vào correlation ID hoặc change ticket. Chỉ dùng định danh tham chiếu.

## 16. Theo dõi consumer và dependency

Sau rotation, owner cần biết những thành phần nào dùng key:

- Ứng dụng mã hóa/giải mã dữ liệu.
- Service thực hiện wrap/unwrap DEK.
- Backup và restore system.
- TLS endpoint hoặc mTLS client.
- JWT issuer và verifier.
- Webhook sender/receiver.
- Certificate validator, trust store hoặc PKI component.
- Job batch, data pipeline và hệ thống archive.

Một key inventory tốt lưu owner và consumer list. Khi event tới, workflow có thể gửi thông báo tới owner, tạo task cập nhật version và chờ xác nhận. Việc tự động hóa phải dựa trên danh sách dependency có nguồn gốc tin cậy, không broadcast secret hoặc key material tới mọi subscriber.

Với key version mới, cần xác minh consumer dùng đúng key ID/version. Với logical key ID tự động rotate trong KMS, consumer có thể không cần đổi ID nhưng vẫn cần xác minh hành vi decrypt/sign và policy. Event schema phải nói rõ có cần consumer action hay không.

## 17. Ví dụ: rotation KEK trong envelope encryption

Giả sử một ứng dụng lưu dữ liệu được mã hóa bằng DEK; DEK được bọc bởi KEK trong KMS. Khi KEK được rotate:

1. KMS tạo key material version mới cho KEK hoặc một KEK resource mới.
2. KMS xác nhận version mới active cho wrap operation.
3. KMS phát key rotated event có key ID và version mới.
4. Event consumer kiểm tra nguồn, deduplicate và tra inventory.
5. Workflow xác định wrapped DEK nào cần rewrap theo semantics của KMS.
6. Ứng dụng hoặc KMS thực hiện rewrap bằng version mới.
7. Kiểm thử unwrap DEK và decrypt dữ liệu mẫu.
8. Theo dõi lỗi decrypt và các operation còn dùng KEK cũ.
9. Giữ version cũ cho decrypt trong thời gian dependency/retention yêu cầu.
10. Chỉ destroy version cũ khi đã xác minh không còn ciphertext hoặc backup cần nó.

Nếu KMS tự quản lý nhiều material version dưới một logical key và tự chọn version cũ khi decrypt, bước rewrap có thể không cần thiết. Nếu thay bằng key resource mới, có thể phải rewrap từng DEK hoặc cập nhật wrapped key metadata. Event phải thể hiện đúng chiến lược đã thực hiện.

## 18. Ví dụ: signing key rotation

Một dịch vụ phát hành JWT bằng private key bất đối xứng:

1. Tạo key pair mới trong HSM hoặc KMS.
2. Cấp key ID mới (kid) và công bố public key tương ứng qua JWKS.
3. Chuyển issuer sang ký token mới bằng private key mới.
4. Verifier tải public key mới và chấp nhận token theo policy.
5. Phát key rotated event liên kết key ID cũ/mới, actor, change ID và thời điểm cutover.
6. Theo dõi token verification failure và verifier cache.
7. Giữ public key cũ trong JWKS cho tới khi token cũ hết hạn và retention cho phép.
8. Disable hoặc retire private key cũ theo policy.
9. Destroy private key cũ khi không còn nhu cầu hợp lệ.

Với HMAC JWT, cả issuer và verifier đều cần secret. Rotation phải phân phối secret mới an toàn tới mọi verifier, có key ID/version và overlap có thời hạn. Không gửi raw secret trong key rotated event.

## 19. Phát hiện rotation bất thường

Các dấu hiệu đáng điều tra:

- Rotation do user hoặc service account không nằm trong allowlist.
- Rotation diễn ra ngoài change window mà không có incident.
- Nhiều key quan trọng bị rotate đồng thời bất thường.
- Key bị rotate liên tục do scheduler loop hoặc automation bug.
- Key version mới có algorithm, key size hoặc purpose khác policy.
- Rotation xảy ra ngay trước hoặc sau một loạt decrypt/export thất bại.
- Actor tạo version mới rồi thay policy/grant để tự cấp quyền.
- Event source không xác thực được hoặc request ID không khớp audit log.
- Event bị mất nhưng current key state cho thấy version đã thay đổi.
- Rotation event được phát nhưng KMS state không phản ánh version mới.

Khi phát hiện, xác minh event bằng audit source gốc và truy vấn trạng thái KMS/HSM. Không chỉ dựa vào message trên event bus. Nếu nghi ngờ actor bị compromise, thu hồi credential và đánh giá các operation khác trong cùng khoảng thời gian.

## 20. Xử lý rotation thất bại

Rotation có thể thất bại vì quota, permission, KMS/HSM outage, key state, provider limitation, policy conflict hoặc lỗi automation. Hệ thống cần phát event failure với thông tin đủ điều tra nhưng không lộ dữ liệu nhạy cảm.

Một event failure nên ghi:

- Key ID/version hiện tại.
- Rotation request ID và trigger.
- Actor/automation identity.
- Thời điểm bắt đầu và kết thúc.
- Error category/code và retryability.
- Bước thất bại: create, activate, publish hoặc consumer migration.
- Trạng thái key sau thất bại.
- Incident/change correlation ID.

Không retry mù quáng nếu chưa biết thao tác có idempotent hay không. Nếu version mới đã được tạo nhưng event publication thất bại, retry có thể phát hiện current state và phát lại event tương ứng thay vì tạo thêm key version. Cần tách lỗi rotation operation khỏi lỗi event delivery.

## 21. Consumer xử lý key rotated event an toàn

Một consumer nên thực hiện:

1. Xác thực nguồn event và schema version.
2. Kiểm tra event ID, event type, key ID và status.
3. Deduplicate theo event_id.
4. Kiểm tra event có đúng key mà consumer sở hữu hoặc phụ thuộc không.
5. Kiểm tra correlation/change/incident reference nếu policy yêu cầu.
6. Truy vấn current key state khi event trễ, thiếu version hoặc có thứ tự bất thường.
7. Chỉ thực hiện hành động đã được allowlist, ví dụ refresh public key cache hoặc lên lịch rewrap.
8. Không tự động export key hoặc thay policy chỉ vì nhận event.
9. Ghi kết quả xử lý và acknowledge sau khi hoàn tất.
10. Gửi failure tới retry/dead-letter workflow có giám sát.

Consumer cần idempotency. Nếu cùng event được gửi lại, nó không được tạo key version mới hoặc thực hiện rewrap nhiều lần ngoài dự kiến. Với thao tác dữ liệu, lưu trạng thái xử lý và transaction boundary phù hợp.

## 22. Retention và bảo vệ audit event

Retention phụ thuộc loại key, dữ liệu được bảo vệ, yêu cầu điều tra và quy định của tổ chức. Audit event có thể cần giữ lâu hơn thời gian một version key còn active vì nó là bằng chứng lịch sử.

Nguyên tắc:

- Xác định retention theo classification và compliance requirement.
- Lưu raw source event và normalized event có thể liên kết với nhau.
- Bảo vệ event bằng encryption at rest và access control.
- Tách quyền xem audit khỏi quyền sử dụng key.
- Có cơ chế legal hold hoặc preservation khi đang điều tra.
- Kiểm tra backup, replica và retention policy của SIEM/log archive.
- Hủy log theo policy sau khi hết thời hạn, trừ khi có yêu cầu giữ lại.

Không lưu key material trong audit log với lý do cần điều tra sau này. Metadata và request reference là đủ cho phần lớn hoạt động kiểm toán; nếu cần forensic evidence bổ sung, dùng quy trình custody riêng.

## 23. Những sai lầm thường gặp

- **Coi rotation scheduled là rotation completed:** chưa có bằng chứng version mới đã active.
- **Phát event thành công khi chỉ nhận request:** tạo trạng thái sai cho consumer.
- **Không phân biệt logical key ID và key version:** khó biết version nào đã thay đổi.
- **Cho rằng rotation đồng nghĩa re-encryption:** có thể dữ liệu cũ vẫn phụ thuộc key version cũ.
- **Destroy key cũ ngay sau rotation:** có thể làm mất khả năng giải mã hoặc xác minh lịch sử.
- **Không có event ID hoặc idempotency:** duplicate message gây thao tác lặp.
- **Tin thứ tự event bus:** event đến trễ có thể làm state bị lùi.
- **Không liên kết change/incident:** không xác định được rotation có được phê duyệt.
- **Ghi raw key hoặc secret vào event:** biến audit pipeline thành nơi rò rỉ key.
- **Chỉ theo dõi KMS, bỏ qua consumer:** rotation hoàn tất nhưng ứng dụng chưa cập nhật.
- **Không giám sát rotation thất bại:** key có thể quá hạn mà không ai nhận biết.
- **Không phát hiện event bị mất:** current state thay đổi nhưng audit pipeline không có bằng chứng.
- **Tự động hành động theo event không xác thực:** attacker có thể kích hoạt workflow giả mạo.
- **Dùng một schema không version:** thay đổi event source làm consumer parse sai.

## 24. Checklist triển khai key rotated event

- [ ] Đã định nghĩa chính xác semantics của key.rotated.
- [ ] Phân biệt scheduled, requested, started, created, activated, failed và destroyed.
- [ ] Event có event ID, event type, schema version và timestamp UTC.
- [ ] Có actor, source, request ID và correlation/change/incident reference.
- [ ] Có key ID và version cũ/mới nếu nguồn cung cấp.
- [ ] Có trigger, status, effective time, purpose và environment/region.
- [ ] Không chứa raw key material, secret, password hoặc plaintext.
- [ ] Event source được xác thực; raw audit evidence được bảo toàn.
- [ ] Event pipeline có encryption, access control và tamper protection.
- [ ] Consumer xử lý duplicate, delay, out-of-order và retry idempotently.
- [ ] Monitoring theo dõi rotation thành công, thất bại, quá hạn và consumer adoption.
- [ ] Alert có severity, owner và runbook cụ thể.
- [ ] Rotation event được liên kết với key inventory, change và incident.
- [ ] Có kiểm thử consumer và xác minh key operation sau cutover.
- [ ] Key version cũ chỉ bị retire/destroy sau khi kiểm tra dependency và retention.
- [ ] Audit event có retention và quyền truy cập phù hợp.

Key rotated event là bằng chứng quan trọng trong quá trình quản lý vòng đời khóa. Event cần phân biệt rõ yêu cầu, tiến trình và kết quả rotation; định danh key/version, actor, trigger và thời điểm; đồng thời được bảo vệ khỏi giả mạo, mất hoặc xử lý lặp. Monitoring phải theo dõi cả trạng thái KMS/HSM lẫn việc consumer chuyển sang version mới. Khi event được liên kết với inventory, change, incident và audit trail, tổ chức có thể chứng minh rotation diễn ra đúng policy, phát hiện bất thường và giữ an toàn cho dữ liệu còn phụ thuộc vào key version cũ.
