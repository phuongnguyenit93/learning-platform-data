# Automated key rotation

Trong chương **Automation và vận hành** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích cách tự động hóa quy trình xoay vòng khóa mật mã. Automated key rotation giúp tạo phiên bản khóa mới theo lịch hoặc theo sự kiện, chuyển workload sang phiên bản mới, xác minh hoạt động và retire phiên bản cũ theo policy. Tự động hóa giảm thao tác thủ công và giúp áp dụng cryptoperiod nhất quán, nhưng chỉ an toàn khi có inventory, dependency mapping, quyền tối thiểu, kiểm tra trước/sau, audit và cơ chế xử lý lỗi.

## 1. Automated key rotation là gì?

**Automated key rotation** là quy trình dùng scheduler, workflow engine, KMS/HSM hoặc automation service để thay đổi key material hoặc chuyển ứng dụng sang key version mới mà không cần operator thực hiện từng bước thủ công.

Một workflow rotation hoàn chỉnh thường gồm:

1. Xác định key đến hạn hoặc cần rotation.
2. Kiểm tra trạng thái, owner, purpose, dependency và policy.
3. Tạo key material hoặc key version mới.
4. Kích hoạt version mới cho operation phù hợp.
5. Cập nhật alias, metadata hoặc consumer configuration nếu cần.
6. Kiểm thử encrypt/decrypt, wrap/unwrap, sign/verify hoặc operation tương ứng.
7. Theo dõi consumer đã chuyển đổi và dữ liệu còn phụ thuộc version cũ.
8. Retire hoặc giới hạn version cũ theo retention policy.
9. Chỉ destruction khi không còn dependency và đã đáp ứng yêu cầu lưu giữ.
10. Ghi audit và thông báo kết quả.

Rotation không đơn giản là tạo key mới rồi xóa key cũ. Hệ thống cần bảo đảm dữ liệu đã mã hóa, chữ ký lịch sử, backup và các consumer vẫn hoạt động trong suốt quá trình chuyển đổi.

## 2. Vì sao cần tự động hóa rotation?

Khóa có cryptoperiod và mức rủi ro phụ thuộc purpose, thuật toán, độ dài, môi trường và lượng dữ liệu được bảo vệ. Nếu rotation hoàn toàn thủ công, tổ chức dễ bỏ lỡ hạn, thực hiện không nhất quán hoặc không có đủ bằng chứng.

Automation có thể:

- Thực hiện rotation đúng lịch và giảm phụ thuộc vào trí nhớ của operator.
- Áp dụng cùng một policy cho nhiều key có cùng purpose.
- Phát hiện key quá hạn hoặc không có owner.
- Tạo key version mới và cập nhật tham chiếu theo workflow chuẩn.
- Gửi cảnh báo khi rotation thất bại hoặc consumer chưa chuyển đổi.
- Ghi nhận actor, trigger, version và kết quả để audit.
- Phối hợp rotation với deployment, backup, KMS/HSM và inventory.

Tự động hóa cũng có thể khuếch đại lỗi. Một policy sai có thể rotate hàng nghìn key, làm hỏng khả năng giải mã hoặc khiến dịch vụ ngừng hoạt động. Vì vậy, mức tự động hóa phải phù hợp với mức độ ảnh hưởng và khả năng phục hồi của từng loại key.

## 3. Phân biệt tự động rotation và tự động re-encryption

Rotation và re-encryption là hai hoạt động khác nhau:

| Hoạt động | Điều thay đổi | Có phải lúc nào cũng cần không? |
|---|---|---|
| Key material rotation | Tạo key material/version mới dưới logical key hoặc key resource | Không phải lúc nào cũng yêu cầu đổi ciphertext |
| Key replacement | Tạo key resource mới và chuyển ứng dụng/alias sang resource mới | Tùy kiến trúc |
| Rewrap DEK | Dùng KEK mới bọc lại DEK hiện có | Thường cần khi thay KEK resource hoặc policy yêu cầu |
| Re-encrypt data | Giải mã dữ liệu bằng key cũ rồi mã hóa bằng DEK mới | Cần khi thay DEK hoặc khi policy yêu cầu |
| Signing key rollover | Chuyển bên ký sang private key mới và cập nhật verifier | Cần phối hợp consumer và thời hạn token/chữ ký |
| Key destruction | Hủy key material và bản sao có thể phục hồi | Chỉ khi dependency và retention đã được xử lý |

Một số KMS quản lý nhiều key material version dưới một logical key. Khi đó, operation mới có thể dùng version hiện hành, còn decrypt ciphertext cũ vẫn tự chọn version cũ. Không cần re-encrypt toàn bộ dữ liệu chỉ vì key material đã được rotate.

Nếu thay bằng key resource mới, ứng dụng có thể phải rewrap DEK hoặc re-encrypt dữ liệu. Workflow phải hiểu semantics của nền tảng và loại key, không suy luận rằng mọi rotation đều có cùng hậu quả.

## 4. Những loại key có thể được tự động rotation

| Loại key | Mục tiêu rotation | Công việc sau khi tạo version mới |
|---|---|---|
| KEK trong KMS | Bảo vệ DEK và key hierarchy | Có thể cần rewrap DEK, hoặc giữ version cũ để unwrap dữ liệu lịch sử |
| DEK | Mã hóa dữ liệu ứng dụng | Re-encrypt dữ liệu hoặc tạo object version mới |
| HMAC/signing secret | Xác thực webhook, API hoặc token | Phân phối secret mới, overlap xác minh và retire secret cũ |
| Asymmetric signing key | Ký JWT, tài liệu hoặc artifact | Công bố public key mới, chuyển signer và giữ public key cũ để verify |
| TLS private key/certificate | Bảo vệ endpoint và xác thực peer | Cấp certificate mới, rollout endpoint và theo dõi client trust |
| Database encryption key | Mã hóa dữ liệu lưu trữ | Phối hợp với database engine, replica và backup |
| Backup/recovery key | Bảo vệ bản sao và quy trình phục hồi | Kiểm tra khả năng restore trước khi retire key cũ |

Không phải key nào cũng nên tự động rotate theo cùng một chu kỳ. CA private key, root key, HSM security domain key hoặc key có quy trình ceremony có thể cần approval và dual control. Automation có thể chuẩn bị hồ sơ, kiểm tra điều kiện và điều phối bước thực hiện, trong khi con người phê duyệt thao tác nhạy cảm.

## 5. Trigger cho automated rotation

Automation có thể bắt đầu từ nhiều loại trigger:

- **Time-based:** key đến hạn cryptoperiod hoặc lịch rotation.
- **Age-based:** key đã tồn tại quá thời gian cho phép.
- **Usage-based:** số operation hoặc lượng dữ liệu sử dụng vượt ngưỡng policy.
- **Event-based:** có thay đổi thuật toán, policy, provider hoặc hệ thống phụ thuộc.
- **Incident-based:** nghi ngờ hoặc xác nhận key bị compromise.
- **Compliance-based:** yêu cầu kiểm soát hoặc audit phát hiện key không đạt baseline.
- **Manual approved:** operator yêu cầu rotation theo change record đã được phê duyệt.

Trigger cần có rule rõ ràng, timezone thống nhất và nguồn thời gian tin cậy. Không nên dùng lịch cron đơn giản cho mọi key mà bỏ qua dependency, maintenance window và giới hạn dịch vụ KMS/HSM.

Rotation theo lịch và rotation khẩn cấp cần workflow khác nhau. Rotation định kỳ có thể có overlap và migration dài hơn; rotation do compromise có thể yêu cầu disable key cũ nhanh chóng, thu hồi credential và chấp nhận tác động availability sau khi đánh giá.

## 6. Xây dựng inventory và dependency trước khi tự động hóa

Automation chỉ an toàn khi biết key đang bảo vệ dữ liệu hoặc dịch vụ nào. Mỗi key nên có metadata tối thiểu:

- Key ID, version, loại key và thuật toán.
- Owner chịu trách nhiệm và nhóm vận hành.
- Purpose: encryption, signing, MAC, TLS, backup hoặc key wrapping.
- Environment, tenant, region và classification.
- Ngày tạo, cryptoperiod, trạng thái và lịch rotation.
- KMS/HSM/provider và policy hiện hành.
- Consumer, application, job, endpoint và hệ thống backup phụ thuộc.
- Dữ liệu hoặc ciphertext còn cần key version cũ.
- RTO/RPO và yêu cầu retention/recovery.

Không tự động rotate key không có owner, không rõ purpose hoặc không có dependency mapping. Trước tiên cần đưa key vào inventory, xác định người chịu trách nhiệm và bổ sung quy trình phục hồi.

Dependency mapping phải bao gồm các consumer ít hoạt động như batch job, archive, disaster recovery, báo cáo lịch sử và bản backup offline. Chỉ kiểm tra traffic hiện tại có thể bỏ sót dữ liệu chỉ được truy cập vài tháng một lần.

## 7. Kiến trúc automation tổng quát

Một kiến trúc thường có các thành phần:

- **Policy/inventory:** xác định key, owner, cryptoperiod và dependency.
- **Scheduler/event trigger:** phát hiện key đến hạn hoặc nhận sự kiện compromise.
- **Orchestrator:** điều phối state machine và lưu tiến độ.
- **KMS/HSM:** tạo, activate, wrap, unwrap, sign hoặc thực hiện operation.
- **Consumer updater:** cập nhật alias, configuration, certificate, public key hoặc wrapped DEK.
- **Verifier:** kiểm thử operation và xác nhận consumer đã chuyển.
- **Audit/event pipeline:** ghi sự kiện và phát thông báo.
- **Monitoring/alerting:** theo dõi tiến độ, lỗi, độ trễ và dependency chưa xử lý.

~~~mermaid
flowchart TD
    A[Key inventory + rotation policy] --> B[Scheduler / event trigger]
    B --> C[Preflight checks]
    C -->|Fail| X[Stop + alert + audit]
    C -->|Pass| D[Rotation orchestrator]
    D --> E[KMS / HSM create new version]
    E --> F[Activate or select new version]
    F --> G[Update consumers / rewrap / re-encrypt]
    G --> H[Verification]
    H -->|Fail| I[Recovery workflow + alert]
    H -->|Pass| J[Retire old version when safe]
    J --> K[Audit + inventory update]
~~~

Orchestrator cần lưu state bền vững. Nếu process restart giữa chừng, workflow phải tiếp tục từ trạng thái đã xác nhận thay vì tạo key version mới hoặc lặp lại thao tác không idempotent.

## 8. Preflight checks trước khi rotate

Trước khi tạo version mới, automation nên kiểm tra:

1. Key tồn tại, đúng owner và đúng environment.
2. Key đang ở trạng thái cho phép rotation.
3. Không có rotation khác đang chạy cho cùng logical key.
4. Policy cho phép principal automation thực hiện action cần thiết.
5. KMS/HSM endpoint, quota và provider đang hoạt động.
6. Dependency inventory đầy đủ và consumer owner đã được xác định.
7. Có backup/recovery path phù hợp với loại key.
8. Có đủ dung lượng, quota và thời gian cho rewrap/re-encryption nếu cần.
9. Maintenance window và approval đã đáp ứng policy.
10. Phiên bản mới tương thích với thuật toán, format và consumer.

Nếu một điều kiện quan trọng không đạt, workflow nên dừng trước khi thay đổi trạng thái key. Không tự động bỏ qua preflight chỉ vì rotation đã quá hạn; trường hợp ngoại lệ cần incident hoặc approval riêng.

## 9. Workflow rotation theo state machine

Thay vì một script dài thực hiện liên tiếp các lệnh không có trạng thái, nên mô hình hóa rotation thành state machine:

| State | Ý nghĩa | Điều kiện chuyển tiếp |
|---|---|---|
| Pending | Đã lên lịch hoặc nhận request | Đến thời điểm và đủ điều kiện |
| Preflight | Kiểm tra inventory, policy và dependency | Tất cả điều kiện bắt buộc đạt |
| Creating | Yêu cầu KMS/HSM tạo version mới | Có kết quả và resource reference |
| Created | Version mới đã tồn tại | Kiểm tra thuộc tính và policy |
| Activating | Chuyển version mới sang dùng cho operation mới | KMS xác nhận trạng thái |
| Migrating | Cập nhật consumer, rewrap hoặc re-encrypt | Các consumer trong scope hoàn tất |
| Verifying | Kiểm tra operation với version mới | Kết quả test đạt |
| Retiring | Hạn chế version cũ theo kế hoạch | Không còn operation mới không được phép |
| Completed | Rotation đạt tiêu chí hoàn tất | Audit và inventory đã cập nhật |
| Failed/Paused | Có lỗi hoặc cần phê duyệt | Có recovery/approval rõ ràng |

Mỗi state transition cần lưu timestamp, actor, request ID, kết quả và lỗi. Không cập nhật inventory thành Completed khi chỉ mới tạo version mới.

## 10. Tạo version mới và activate an toàn

KMS/HSM có thể hỗ trợ native automatic rotation hoặc API tạo key version mới. Cần xác định chính xác hành vi:

- Logical key ID có giữ nguyên không?
- Version mới có tự động active cho encrypt/sign không?
- Decrypt/verify với ciphertext/chữ ký cũ được xử lý ra sao?
- Có thể chọn version tường minh cho operation không?
- Version cũ có thể chuyển sang decrypt-only hoặc verify-only không?
- Có cần cập nhật alias hoặc consumer configuration không?

Sau khi tạo version, kiểm tra key type, algorithm, key size, purpose, policy và trạng thái. Không activate version chỉ dựa vào việc API tạo key trả về thành công.

Nếu hệ thống dùng alias, cập nhật alias cần có kiểm soát cạnh tranh. Một consumer có thể đọc alias trong lúc alias đang chuyển đổi; cần đảm bảo request đang chạy không trộn metadata của version cũ với version mới.

## 11. Consumer migration và overlap

Nhiều ứng dụng cần thời gian để chuyển sang key version mới. Một số giao thức hỗ trợ giai đoạn overlap:

- Signer bắt đầu ký bằng key mới.
- Verifier chấp nhận key mới và key cũ trong thời gian giới hạn.
- Encryptor dùng key mới cho dữ liệu mới.
- Decryptor tiếp tục hỗ trợ key cũ cho ciphertext lịch sử.
- Endpoint triển khai certificate mới trong khi client cập nhật trust/cache.

Overlap cần có thời điểm bắt đầu, kết thúc và điều kiện retire rõ ràng. Không giữ key cũ active để tạo dữ liệu mới sau cutover nếu policy yêu cầu dùng version mới.

Consumer updater nên sử dụng API/configuration được kiểm soát, xác nhận deployment version và chờ health check. Không broadcast key material tới consumer nếu họ chỉ cần key ID, public key hoặc quyền gọi KMS.

## 12. KEK rotation trong envelope encryption

Trong envelope encryption, DEK mã hóa dữ liệu và KEK bảo vệ DEK. Khi rotate KEK:

1. Tạo hoặc activate KEK version mới.
2. Xác định wrapped DEK và metadata đang dùng KEK cũ.
3. Kiểm tra KMS hỗ trợ automatic version handling hay cần rewrap.
4. Nếu cần rewrap, dùng KMS/HSM unwrap DEK bằng quyền được cấp rồi wrap lại bằng KEK mới.
5. Cập nhật wrapped DEK metadata một cách nguyên tử.
6. Kiểm thử unwrap DEK mới và decrypt dữ liệu mẫu.
7. Theo dõi lỗi và operation còn dùng version cũ.
8. Giữ KEK cũ cho tới khi mọi wrapped DEK, backup và replica đã được xử lý.

Nếu KMS tự quản lý key material versions dưới một logical key, decrypt ciphertext cũ có thể tự động dùng version phù hợp. Khi đó không cần rewrap mọi DEK chỉ vì rotation nội bộ đã diễn ra. Phải dựa vào semantics của dịch vụ.

Không đưa DEK plaintext vào log, queue hoặc event. Nếu ứng dụng phải nhận DEK trong bộ nhớ, giới hạn quyền, thời gian tồn tại và khả năng tạo heap dump.

## 13. DEK rotation và re-encryption dữ liệu

DEK rotation có thể yêu cầu mã hóa lại dữ liệu vì ciphertext thường phụ thuộc trực tiếp vào DEK cũ. Với lượng dữ liệu lớn, workflow cần:

- Lập danh sách object/record và DEK version hiện tại.
- Chia batch có giới hạn và checkpoint.
- Đọc ciphertext, giải mã bằng DEK cũ và mã hóa bằng DEK mới.
- Xác thực tag/integrity trước khi chấp nhận plaintext.
- Ghi ciphertext mới và metadata version theo transaction hoặc atomic object replacement.
- Kiểm tra checksum, số lượng record và khả năng đọc sau migration.
- Retry object lỗi mà không làm hỏng bản gốc.
- Giữ dữ liệu/key cũ trong thời gian rollback hoặc recovery được phê duyệt.

Không xóa ciphertext cũ ngay khi một batch thành công. Cần xác minh toàn bộ partition, replica, backup, archive và consumer trước khi retire DEK cũ. Nếu dữ liệu không thể giải mã hoặc tag không hợp lệ, dừng batch và điều tra; không ghi đè bản gốc bằng kết quả chưa xác minh.

## 14. Signing key và certificate rotation

Với asymmetric signing key, automation thường tạo key pair mới trong HSM/KMS, sau đó cập nhật public key cho verifier:

1. Tạo private/public key pair mới.
2. Gán key ID hoặc kid mới.
3. Cập nhật JWKS, certificate hoặc trust distribution.
4. Chuyển signer sang private key mới.
5. Xác nhận verifier đã tải public key mới.
6. Theo dõi lỗi xác minh, cache và token còn hiệu lực.
7. Giữ public key cũ cho chữ ký/token lịch sử trong thời gian cần thiết.
8. Disable/retire private key cũ và destroy khi đủ điều kiện.

Với TLS certificate rotation, cần kiểm tra hostname/SAN, chain, validity, EKU, key usage, endpoint rollout và client trust. Chỉ tạo certificate mới không chứng minh mọi endpoint đã trình bày certificate mới.

Với HMAC signing secret, cả signer và verifier đều cần shared secret. Automation phải phân phối secret version mới qua secret manager hoặc kênh cấp phát đã xác thực, có overlap và key ID. Không gửi secret trong event hoặc log.

## 15. Idempotency và xử lý chạy lặp

Scheduler có thể kích hoạt cùng một workflow nhiều lần do timeout, retry hoặc nhiều worker cùng nhận một job. Rotation operation không phải lúc nào cũng idempotent: gọi create key nhiều lần có thể tạo nhiều version không cần thiết.

Các biện pháp:

- Gán rotation_job_id duy nhất cho mỗi lần chạy.
- Dùng idempotency token nếu API KMS/HSM hỗ trợ.
- Lưu trạng thái workflow bền vững.
- Dùng distributed lock hoặc cơ chế lease theo logical key.
- Kiểm tra current key state trước khi tạo version.
- Nếu request timeout, truy vấn trạng thái theo request ID trước khi retry.
- Chỉ một workflow được quyền activate/alias switch cho cùng key tại một thời điểm.
- Consumer xử lý event bằng event ID và deduplication.

Lock cần có lease/expiry để không bị giữ vĩnh viễn khi worker crash. Tuy nhiên, lease hết hạn không đủ để chứng minh worker cũ đã dừng; thao tác cập nhật cần fencing token hoặc kiểm tra generation để tránh worker cũ ghi đè state mới.

## 16. Retry, timeout và failure recovery

Không phải mọi lỗi đều nên retry:

| Nhóm lỗi | Cách xử lý |
|---|---|
| Throttle/quota tạm thời | Retry có exponential backoff và jitter, giới hạn số lần |
| Network timeout, chưa rõ operation đã hoàn tất | Tra cứu request/resource state trước khi gửi lại |
| Permission denied | Dừng và cảnh báo; không retry liên tục |
| Invalid key state hoặc policy conflict | Pause workflow, yêu cầu điều tra/approval |
| HSM/KMS outage | Retry theo health state và runbook DR; không tạo key ngoài quy trình |
| Consumer migration failure | Giữ version cũ khả dụng, retry consumer theo checkpoint |
| Integrity/authentication failure | Dừng xử lý dữ liệu liên quan và mở incident nếu cần |
| Audit/event publication failure | Khôi phục delivery từ outbox/source log; không tạo rotation mới chỉ để phát lại event |

Workflow cần tách kết quả rotation operation khỏi kết quả publish event. Có thể key đã rotate thành công nhưng event bus tạm thời lỗi. Khi đó cần phát lại event từ audit/outbox có định danh ổn định, không thực hiện rotation lần nữa.

## 17. Rollback và khả năng phục hồi

Rotation không phải lúc nào cũng có rollback theo nghĩa đưa hệ thống trở lại key cũ. Nếu version mới đã mã hóa dữ liệu hoặc tạo chữ ký, việc quay lại version cũ có thể không giải quyết được dependency và có thể làm trạng thái phức tạp hơn.

Thiết kế recovery cần:

- Giữ version cũ ở trạng thái decrypt-only/verify-only khi phù hợp.
- Không destroy key cũ trước khi migration và retention hoàn tất.
- Có checkpoint và bản sao dữ liệu để khôi phục batch re-encryption.
- Dùng atomic update cho alias hoặc wrapped DEK metadata.
- Có thể chuyển signer về key cũ trong giai đoạn overlap nếu key cũ chưa compromise và policy cho phép.
- Nếu key cũ bị compromise, không kích hoạt lại chỉ để rollback; phải chuyển sang incident response.
- Ghi rõ điều kiện rollback, người phê duyệt và thời hạn.

Đối với dữ liệu đã re-encrypt, phục hồi có thể yêu cầu khôi phục ciphertext/metadata trước migration và key version tương ứng. Vì vậy cần kiểm tra restore path trước khi bắt đầu batch lớn.

## 18. Rotation khẩn cấp do compromise

Rotation định kỳ và rotation do compromise có mục tiêu khác nhau. Khi key bị lộ, chỉ tạo version mới chưa đủ vì attacker có thể tiếp tục dùng key cũ hoặc đã có bản sao key material.

Workflow khẩn cấp có thể:

1. Xác nhận key ID/version và phạm vi bị ảnh hưởng.
2. Disable hoặc revoke operation của key cũ theo incident policy.
3. Thu hồi credential, grant và session có thể bị lộ.
4. Tạo key mới trong miền bảo vệ đã xác minh.
5. Cập nhật consumer và policy để chỉ dùng key mới.
6. Đánh giá dữ liệu, ciphertext, signature, token và backup đã phụ thuộc key cũ.
7. Re-encrypt, rewrap hoặc phát hành lại credential/chứng thư khi cần.
8. Giám sát operation tiếp tục nhắm vào key cũ.
9. Lưu audit và bằng chứng phục vụ điều tra.

Không giữ overlap với key bị compromise theo thói quen rotation định kỳ. Nếu cần verify chữ ký hoặc giải mã dữ liệu lịch sử, tạo một đường xử lý hạn chế, có phê duyệt và giám sát riêng; không cho phép key cũ tiếp tục ký hoặc mã hóa dữ liệu mới.

## 19. Quyền của rotation automation

Automation service cần quyền đủ để hoàn thành workflow nhưng không nên có quyền quản trị toàn bộ KMS.

Một bộ quyền có thể gồm:

- Đọc metadata và trạng thái key trong scope được giao.
- Tạo version hoặc yêu cầu native rotation cho key được phép.
- Activate version hoặc cập nhật alias theo policy.
- Gọi operation cần cho rewrap/verification.
- Đọc audit status và phát event.
- Cập nhật inventory/workflow state.

Các quyền nên tách hoặc bị cấm mặc định:

- Export raw key material.
- Thay đổi key policy hoặc cấp quyền cho chính mình.
- Xóa key hoặc schedule destruction.
- Truy cập mọi tenant/environment.
- Decrypt dữ liệu nghiệp vụ không thuộc scope rotation.
- Tắt audit hoặc thay retention.

Với thao tác nhạy cảm, dùng approval/dual control hoặc human-in-the-loop. Credential của automation nên là workload identity ngắn hạn, không phải access key tĩnh đặt trong script.

## 20. Monitoring và alerting

Theo dõi cả tiến trình lẫn kết quả thực tế:

| Metric/event | Ý nghĩa |
|---|---|
| Keys due for rotation | Số key đến hạn hoặc quá hạn |
| Rotation success/failure | Tỷ lệ workflow hoàn tất và thất bại |
| Rotation duration | Thời gian từ trigger đến activation/completion |
| Consumer migration lag | Độ trễ consumer chuyển sang version mới |
| Old-version operation count | Số operation còn dùng version cũ |
| Rewrap/re-encryption progress | Số DEK/object đã xử lý và còn tồn |
| Decrypt/sign failure rate | Lỗi phát sinh sau cutover |
| Retry and throttle count | Dấu hiệu quota hoặc service instability |
| Missing audit/event count | Rotation không có bằng chứng hoặc event pipeline lỗi |
| Key age/cryptoperiod drift | Key vượt thời hạn policy |

Alert nên phát khi rotation production thất bại, key quá hạn, consumer chưa chuyển trong thời hạn, operation cũ tiếp tục sau retirement hoặc xuất hiện rotation không có approval. Mỗi alert cần owner, severity, runbook và điều kiện đóng.

Dashboard nên phân nhóm theo purpose, environment, owner và criticality. Không chỉ hiển thị số lượng rotation thành công; cần chỉ ra dependency chưa hoàn tất và key version cũ vẫn còn được sử dụng.

## 21. Audit và event cho automated rotation

Mỗi workflow cần lưu:

- Rotation job ID và event ID.
- Key ID, logical key ID và old/new version nếu nguồn cung cấp.
- Trigger, policy version và cryptoperiod.
- Actor/workload identity và approval reference.
- Timestamp cho từng state transition.
- KMS/HSM request ID và kết quả.
- Consumer đã cập nhật, operation verify và test result.
- Lỗi, retry, pause/resume và recovery action.
- Thời điểm retire/disable/destroy nếu đã thực hiện.

Event success chỉ được phát khi điều kiện success đã định nghĩa đạt. Nếu chỉ tạo version mới mà consumer chưa migrate, nên phát event riêng như key.version.created hoặc rotation.phase.completed, không tuyên bố toàn bộ workflow hoàn tất.

Audit không ghi key bytes, password, secret, plaintext hoặc wrapped key material. Log cần được bảo vệ khỏi sửa đổi và quyền quản trị audit nên tách khỏi quyền của rotation automation.

## 22. Lịch rotation và điều phối tải

Nếu hàng nghìn key cùng đến hạn một thời điểm, scheduler có thể tạo tải đột biến cho KMS/HSM, consumer và event pipeline.

Các kỹ thuật điều phối:

- Jitter thời điểm chạy trong một cửa sổ được policy cho phép.
- Giới hạn concurrency theo account, region, HSM partition và key purpose.
- Chia batch theo owner hoặc dependency group.
- Ưu tiên key criticality và key quá hạn.
- Tránh rotation đồng thời các key có chung dependency nếu có thể làm gián đoạn dịch vụ.
- Theo dõi quota và throttle trước khi tăng concurrency.
- Có pause switch để dừng workflow mới khi có incident.

Jitter không được làm vượt cryptoperiod tối đa hoặc deadline tuân thủ. Với key quan trọng, cần lịch được phê duyệt và có khả năng ưu tiên thay vì chỉ random thời điểm.

## 23. Ví dụ cấu hình rotation policy

Ví dụ YAML dưới đây minh họa policy logic cho một KEK dùng trong production:

~~~yaml
rotation_policy:
  name: orders-kek-production
  key_id: orders-kek-prod
  purpose: envelope-encryption
  environment: production
  rotation:
    mode: scheduled
    cryptoperiod_days: 180
    jitter_window_hours: 24
    max_concurrent_jobs: 1
  preconditions:
    owner_required: true
    dependency_inventory_required: true
    recovery_test_required: true
    approval_required: true
  workflow:
    create_new_version: true
    activate_after_validation: true
    rewrap_required: provider_dependent
    verify_decrypt: true
    retain_old_version_days: policy_defined
    destroy_old_version_automatically: false
  controls:
    default_deny: true
    export_allowed: false
    audit_required: true
    alert_on_failure: true
~~~

Đây là ví dụ mô hình hóa, không phải schema dùng trực tiếp cho một KMS cụ thể. Cryptoperiod và retention phải dựa trên policy của tổ chức, chuẩn áp dụng và phân tích rủi ro. Đặc biệt, không đặt destruction tự động nếu chưa có dependency proof và phê duyệt phù hợp.

## 24. Ví dụ pseudo-workflow

Logic orchestration có thể được biểu diễn như sau:

~~~text
job = load_rotation_job(rotation_job_id)
if job.state == COMPLETED:
    return existing_result

acquire_lock(job.logical_key_id, fencing_token)
try:
    assert_owner_and_policy(job)
    assert_no_conflicting_rotation(job)
    assert_recovery_and_dependency_ready(job)

    if not job.new_version_id:
        job.new_version_id = create_or_find_version(
            idempotency_token=job.rotation_job_id
        )
        persist(job, state=CREATED)

    validate_key_attributes(job.new_version_id)
    activate_version_if_policy_allows(job)
    persist(job, state=ACTIVATED)

    migrate_consumers_or_rewrap_if_required(job)
    verify_crypto_operations(job)
    verify_consumer_adoption(job)
    persist(job, state=VERIFIED)

    retire_old_version_when_safe(job)
    publish_completion_event_once(job)
    update_inventory(job, state=COMPLETED)
finally:
    release_lock_if_owned(job.logical_key_id, fencing_token)
~~~

Pseudo-workflow nhấn mạnh việc lưu checkpoint và tìm lại version đã tạo sau timeout. Triển khai thật cần xử lý crash giữa các bước, transaction boundary, idempotency API, quyền và trạng thái KMS/HSM. Không xem try/finally là cơ chế đảm bảo mọi thao tác đã được rollback nếu process hoặc host bị dừng đột ngột.

## 25. Kiểm thử automation trước production

Trước khi bật rotation tự động cho key production, cần kiểm thử:

- Trigger đúng key đến hạn và bỏ qua key chưa đến hạn.
- Default deny khi thiếu owner, purpose, approval hoặc dependency.
- Chỉ một workflow chạy cho cùng logical key.
- Timeout sau khi KMS tạo version nhưng trước khi lưu response.
- Event publish thất bại sau khi rotation đã hoàn tất.
- Consumer nhận event trùng hoặc sai thứ tự.
- Consumer không tương thích với algorithm/key version mới.
- Rewrap hoặc re-encryption thất bại giữa batch.
- KMS/HSM throttle, outage hoặc permission bị thu hồi.
- Restore dữ liệu và decrypt bằng version được giữ lại.
- Retire không xảy ra khi còn dependency.
- Rotation compromise path disable key cũ theo đúng incident policy.

Chạy dry-run để hiển thị key sẽ bị tác động, dependency, action, thời gian và approval cần thiết. Dry-run không thay thế test thực tế trên key test và dữ liệu thử nghiệm.

## 26. Những sai lầm thường gặp

- **Chỉ tạo key version mới rồi đánh dấu Completed:** consumer và dữ liệu có thể chưa chuyển đổi.
- **Coi rotation là re-encryption:** có thể ciphertext vẫn phụ thuộc key cũ.
- **Không kiểm tra inventory/dependency:** bỏ sót backup, archive hoặc batch job.
- **Không có idempotency:** retry tạo nhiều key version.
- **Không khóa cạnh tranh:** hai workflow cùng activate hoặc đổi alias.
- **Retry mù khi timeout:** thao tác đã thành công nhưng bị lặp.
- **Xóa key cũ ngay:** dữ liệu lịch sử có thể mất khả năng giải mã.
- **Bật lại key bị compromise để rollback:** khôi phục đường tấn công.
- **Automation có quyền admin rộng:** một lỗi script có thể tác động toàn bộ key.
- **Không giới hạn concurrency:** gây throttle hoặc outage KMS/HSM.
- **Phát success event quá sớm:** monitoring và consumer hiểu sai trạng thái.
- **Không có pause/kill switch:** lỗi lan rộng trước khi operator can thiệp.
- **Không test restore:** rotation thành công nhưng recovery thất bại.
- **Không theo dõi consumer cũ:** version cũ tiếp tục được sử dụng ngoài dự kiến.

## 27. Checklist triển khai automated key rotation

- [ ] Key có owner, purpose, criticality và inventory đầy đủ.
- [ ] Cryptoperiod và trigger được định nghĩa theo policy.
- [ ] Đã xác định native rotation hay workflow thay key resource.
- [ ] Đã hiểu semantics version và khả năng decrypt dữ liệu cũ của KMS/HSM.
- [ ] Dependency bao gồm application, batch, backup, archive và DR.
- [ ] Preflight kiểm tra policy, approval, quota, recovery và trạng thái key.
- [ ] Workflow có state machine và checkpoint bền vững.
- [ ] Có idempotency token, lock/lease và fencing khi cần.
- [ ] Retry có phân loại lỗi, backoff, giới hạn và kiểm tra state sau timeout.
- [ ] Consumer migration, overlap và verification có tiêu chí hoàn tất.
- [ ] Rewrap/re-encryption có checkpoint, integrity check và recovery path.
- [ ] Version cũ chỉ retire/destroy sau dependency và retention check.
- [ ] Rotation automation dùng workload identity và least privilege.
- [ ] Có approval/dual control cho key và thao tác critical.
- [ ] Audit ghi actor, trigger, version, state transition và kết quả.
- [ ] Monitoring theo dõi failure, overdue, lag, old-version use và event delivery.
- [ ] Có pause switch, incident workflow và runbook rõ ràng.
- [ ] Đã dry-run, kiểm thử failure mode và diễn tập restore.

Automated key rotation giúp tổ chức thực hiện cryptoperiod nhất quán và giảm sai sót thủ công, nhưng chỉ hoàn tất khi version mới được sử dụng đúng, consumer đã chuyển đổi và khả năng giải mã/xác minh lịch sử vẫn được bảo đảm. Workflow cần inventory và dependency đầy đủ, preflight, state machine, idempotency, retry có kiểm soát, audit và monitoring. Version cũ chỉ được retire hoặc destroy sau khi có bằng chứng không còn phụ thuộc; với key bị compromise, phải dùng incident response thay vì rollback mù quáng.
