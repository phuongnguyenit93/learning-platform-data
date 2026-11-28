# Rotation failure handling

Trong chương **Automation và vận hành** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích cách xử lý lỗi trong quy trình xoay vòng khóa mật mã. Rotation có thể thất bại trước khi tạo key version mới, sau khi KMS/HSM đã tạo version, trong lúc chuyển consumer, khi rewrap/re-encrypt dữ liệu hoặc khi phát audit event. Cách xử lý phải dựa trên trạng thái thực tế của key và dữ liệu, phân biệt lỗi tạm thời với lỗi không thể retry, bảo toàn khả năng giải mã và tránh kích hoạt lại key đã bị compromise.

## 1. Rotation failure handling là gì?

**Rotation failure handling** là tập hợp cơ chế phát hiện, phân loại, cô lập, khôi phục và ghi nhận lỗi xảy ra trong quá trình key rotation. Mục tiêu là đưa workflow về một trạng thái an toàn, giữ dữ liệu có thể đọc được và tránh tạo thêm rủi ro khi automation retry hoặc operator can thiệp.

Một workflow rotation có thể gồm nhiều hệ thống: scheduler, orchestrator, KMS/HSM, secret manager, consumer updater, database, event bus, audit pipeline và ứng dụng. Lỗi ở bất kỳ bước nào cũng có thể làm trạng thái giữa các thành phần không đồng nhất.

Failure handling cần trả lời:

- Bước nào đã hoàn tất và bước nào chưa?
- KMS/HSM đã tạo hoặc activate key version mới chưa?
- Có consumer nào đã dùng version mới để tạo ciphertext hoặc chữ ký chưa?
- Dữ liệu đã được rewrap hoặc re-encrypt một phần chưa?
- Version cũ còn cần để decrypt hoặc verify không?
- Có thể retry an toàn hay cần dừng để điều tra?
- Cần forward recovery, compensation hay incident response?
- Ai chịu trách nhiệm và bằng chứng audit nào phải được lưu?

Không đánh dấu rotation Completed chỉ vì request đã được gửi hoặc key version mới đã được tạo. Trạng thái hoàn tất phải phản ánh tiêu chí đã định nghĩa cho đúng loại key và workflow.

## 2. Vì sao rotation có thể thất bại?

Các nguyên nhân thường gặp:

- KMS/HSM không khả dụng, bị throttle hoặc hết quota.
- Network timeout khiến client không biết operation đã hoàn tất hay chưa.
- Principal thiếu quyền tạo, activate, wrap, unwrap hoặc cập nhật alias.
- Key đang disabled, pending deletion hoặc ở trạng thái không cho phép rotation.
- Provider không hỗ trợ thuật toán, key size hoặc parameter mới.
- Consumer chưa nhận cấu hình, public key hoặc secret version mới.
- Rewrap/re-encryption thất bại giữa một batch.
- Database hoặc object storage không ghi metadata nguyên tử.
- Event bus, audit sink hoặc inventory service bị gián đoạn.
- Workflow chạy đồng thời, retry lặp hoặc worker cũ ghi đè state mới.
- Key compromise, dữ liệu integrity check thất bại hoặc phát hiện dependency bị bỏ sót.

Không phải mọi lỗi đều có cùng cách xử lý. Throttle tạm thời có thể retry; permission denied thường cần sửa policy; authentication tag failure cần dừng xử lý dữ liệu; key compromise cần incident response. Dùng một retry loop chung cho mọi lỗi có thể làm tình hình xấu hơn.

## 3. Các nguyên tắc cốt lõi

1. **Preserve recoverability:** giữ key version và dữ liệu cần thiết để tiếp tục decrypt/verify.
2. **Know the actual state:** xác minh KMS/HSM và consumer state trước khi thực hiện bước tiếp theo.
3. **Retry only when safe:** chỉ retry lỗi tạm thời hoặc operation có idempotency rõ ràng.
4. **Prefer forward recovery:** sửa nguyên nhân và tiếp tục workflow khi trạng thái đã thay đổi không thể đảo ngược an toàn.
5. **Never revive a compromised key:** không bật lại key bị lộ chỉ để khôi phục availability.
6. **Keep original data until verified:** không ghi đè ciphertext gốc trước khi dữ liệu mới được xác minh.
7. **Audit every transition:** ghi actor, request, key version, trạng thái, quyết định và kết quả.
8. **Limit blast radius:** pause workflow theo key hoặc nhóm dependency thay vì dừng hay thay đổi toàn bộ hệ thống khi không cần.

Failure handling cần có owner, runbook và điều kiện kết thúc rõ ràng. Một workflow ở trạng thái Paused hoặc NeedsReview tốt hơn việc báo thành công trong khi dữ liệu chưa được bảo đảm.

## 4. Phân loại lỗi theo khả năng retry

| Nhóm lỗi | Ví dụ | Cách xử lý ban đầu |
|---|---|---|
| Transient | Throttle, service unavailable, network reset | Retry có backoff sau khi xác định operation an toàn |
| Ambiguous outcome | Timeout sau khi gửi create/activate request | Tra cứu trạng thái bằng request ID/idempotency token trước khi retry |
| Permanent configuration | Sai algorithm, parameter, provider hoặc format | Dừng workflow, sửa cấu hình và review |
| Authorization | Permission denied, grant hết hạn | Dừng; kiểm tra principal, policy và approval |
| Invalid state | Key disabled, pending deletion hoặc version không hợp lệ | Pause; xác minh key state và dependency |
| Data integrity | AEAD tag sai, checksum mismatch, signature invalid | Dừng xử lý dữ liệu; điều tra nguồn và bản gốc |
| Consumer incompatibility | Workload không hỗ trợ version/algorithm mới | Giữ khả năng đọc version cũ; cập nhật consumer |
| Operational dependency | Event bus, inventory hoặc audit sink lỗi | Phân tách lỗi rotation khỏi lỗi notification/recording |
| Security incident | Key compromise hoặc actor trái phép | Cô lập, revoke/disable theo incident policy và điều tra |
| Irrecoverable loss | Key material duy nhất bị destroy hoặc mất backup | Kích hoạt incident về mất dữ liệu; không giả định có thể tái tạo key |

Phân loại phải dựa trên mã lỗi và trạng thái nguồn. Ví dụ, một network timeout không chứng minh KMS operation thất bại; một response 403 không phải lỗi transient để retry liên tục.

## 5. State machine và trạng thái lỗi

Rotation nên được điều phối bằng state machine bền vững thay vì chỉ dựa vào tiến trình script đang chạy:

| State | Ý nghĩa | Xử lý khi lỗi |
|---|---|---|
| Pending | Job đã được lên lịch | Có thể hủy hoặc reschedule trước side effect |
| Preflight | Kiểm tra policy, inventory và dependency | Dừng nếu thiếu điều kiện |
| Creating | Gửi yêu cầu tạo version | Nếu outcome chưa rõ, tra cứu request/resource |
| Created | Version mới đã tồn tại | Giữ version ở trạng thái chưa active nếu cần điều tra |
| Activating | Chuyển version mới sang operation mới | Xác minh current version trước khi thử lại |
| Migrating | Chuyển consumer, rewrap hoặc re-encrypt | Pause theo checkpoint; giữ version cũ |
| Verifying | Kiểm tra operation và dữ liệu | Không retire version cũ khi verify chưa đạt |
| Retiring | Hạn chế version cũ | Kiểm tra dependency và trạng thái thực tế |
| Completed | Đạt tiêu chí thành công | Cập nhật inventory và audit |
| Paused/NeedsReview | Chờ điều tra hoặc phê duyệt | Chỉ resume sau khi có quyết định rõ |
| Failed | Không thể tiếp tục theo workflow hiện tại | Ghi nguyên nhân, side effect và recovery plan |

State phải mô tả sự thật đã xác nhận. Nếu KMS đã tạo version nhưng worker crash trước khi lưu response, job không nên quay lại Pending và tạo thêm key. Nó phải tra cứu theo idempotency token, request ID hoặc metadata đã gắn với operation.

## 6. Timeout và kết quả không chắc chắn

Đây là tình huống dễ gây lỗi lặp: automation gửi request tạo key version, KMS thực hiện thành công nhưng response bị mất trên đường truyền. Client chỉ thấy timeout.

Quy trình an toàn:

1. Ghi lại rotation job ID, idempotency token, request ID và key ID.
2. Không lập tức gửi một create request mới.
3. Truy vấn trạng thái operation hoặc tài nguyên theo reference đã lưu.
4. Kiểm tra version mới có tồn tại không, thuộc đúng key không và trạng thái là gì.
5. Nếu đã tạo, tiếp tục từ state Created.
6. Nếu nguồn xác nhận chưa tạo, retry theo policy.
7. Nếu không thể xác định, chuyển NeedsReview hoặc dùng reconciliation procedure.

Nếu API hỗ trợ idempotency token, dùng token ổn định cho cùng một logical operation. Không tạo token mới mỗi lần retry vì điều đó có thể khiến KMS xem request là một thao tác khác.

Không dựa riêng vào tên hoặc timestamp gần giống để kết luận một version là kết quả của job. Dùng request reference, tag/metadata có kiểm soát hoặc audit source được nền tảng hỗ trợ.

## 7. Retry, backoff và giới hạn

Retry chỉ phù hợp với lỗi transient hoặc operation có thể xác định trạng thái an toàn. Một chiến lược thường dùng:

- Exponential backoff để tăng khoảng cách giữa các lần thử.
- Jitter để tránh nhiều worker retry cùng lúc.
- Giới hạn số lần thử và tổng thời gian.
- Tôn trọng Retry-After hoặc quota response nếu dịch vụ cung cấp.
- Dùng circuit breaker khi dependency lỗi kéo dài.
- Dừng retry khi gặp permission, invalid state, policy conflict hoặc integrity error.
- Đưa job sang hàng đợi xử lý thủ công khi vượt retry budget.

Ví dụ pseudo-logic:

~~~text
for attempt in bounded_retry_budget:
    result = call_operation()

    if result.success:
        persist_confirmed_state()
        break

    if result.outcome_is_ambiguous:
        state = query_operation_by_idempotency_reference()
        if state.is_completed:
            persist_confirmed_state()
            break
        if state.is_unknown:
            pause_for_reconciliation()
            break

    if result.is_permanent_or_security_error:
        pause_and_alert()
        break

    wait(exponential_backoff_with_jitter(attempt))
else:
    move_to_manual_review()
~~~

Đây là logic minh họa. Thời gian retry phải phù hợp SLA, quota KMS/HSM và mức độ quan trọng của key. Không để retry loop vô hạn giữ lock, tạo tải hoặc che khuất một incident.

## 8. Idempotency, lock và fencing

Nhiều workflow có thể chạy cùng lúc do scheduler trùng, message duplicate hoặc worker retry. Nếu cả hai cùng rotate một logical key, có thể tạo nhiều version, chuyển alias qua lại hoặc cập nhật metadata sai thứ tự.

Các biện pháp:

- Một rotation job ID duy nhất cho mỗi lần rotation logic.
- Idempotency token ổn định cho API hỗ trợ.
- Distributed lock/lease theo logical key.
- Fencing token hoặc generation number để worker cũ không ghi đè state mới.
- Persist checkpoint sau từng side effect đã xác nhận.
- Deduplicate event theo event ID.
- Dùng compare-and-set/version check khi cập nhật alias hoặc metadata.

Lock chỉ giảm khả năng chạy đồng thời; nó không chứng minh worker cũ đã dừng sau khi lease hết hạn. Mọi update quan trọng nên kiểm tra fencing token hoặc generation hiện tại. Không cho một worker cũ tiếp tục activate version sau khi quyền sở hữu workflow đã chuyển sang worker mới.

## 9. Lỗi khi tạo key version mới

### Preflight thất bại

Nếu owner, policy, approval, quota hoặc dependency chưa đạt, dừng trước khi gọi KMS/HSM. Ghi lý do và giao owner xử lý. Không tự động bỏ qua điều kiện để giữ lịch rotation.

### KMS/HSM từ chối tạo key

Kiểm tra principal, key policy, service quota, thuật toán, key size, HSM partition và trạng thái resource. Permission denied hoặc invalid parameter không nên retry liên tục.

### Version được tạo nhưng không đúng thuộc tính

Không activate. Kiểm tra key type, algorithm, size, purpose, origin, extractability và policy. Nếu version không đáp ứng yêu cầu, cô lập theo cơ chế nền tảng và tạo change/incident để xử lý; không sử dụng chỉ vì đã tồn tại.

### Version được tạo nhưng response bị mất

Tra cứu theo request/idempotency reference và tiếp tục từ state đã xác nhận. Không tạo version thứ hai chỉ để có response mới.

## 10. Lỗi khi activate hoặc chuyển alias

Activation có thể thất bại vì key state, policy, concurrency hoặc API outage. Nếu không rõ activation đã xảy ra hay chưa:

1. Đọc current primary/active version từ nguồn có thẩm quyền.
2. Đối chiếu audit event và request ID.
3. Kiểm tra alias hoặc routing thực tế.
4. Xác định consumer nào đã bắt đầu dùng version mới.
5. Chỉ gửi lại activation khi state và semantics của API cho phép.

Nếu alias đã chuyển nhưng inventory chưa cập nhật, ưu tiên reconciliation từ current state và audit source. Không chuyển alias về version cũ chỉ để khớp inventory.

Nếu một số consumer đã đọc alias cũ trong lúc cutover, cần xác định request nào đang chạy, metadata nào đã ghi và liệu ciphertext có được tạo bằng version cũ hay mới. Giữ cả hai version có thể cần thiết cho decrypt trong giai đoạn chuyển tiếp.

## 11. Lỗi trong consumer migration

Consumer có thể không nhận cấu hình mới, cache key ID cũ, chưa tải public key mới hoặc không hỗ trợ thuật toán/version mới.

Cách xử lý:

- Xác định danh sách consumer theo inventory và telemetry.
- Dừng retire version cũ trong khi consumer còn hợp lệ cần nó.
- Kiểm tra rollout, secret manager refresh, JWKS cache, certificate chain và provider support.
- Cập nhật từng nhóm consumer theo canary hoặc batch.
- Xác minh health check và operation thực tế sau cập nhật.
- Theo dõi consumer cũ còn gửi request sau cutover.
- Không phân phối raw secret/key material nếu consumer chỉ cần key ID hoặc public key.

Nếu consumer không thể nâng cấp trong thời hạn, owner phải quyết định compatibility plan hoặc exception có thời hạn. Không để overlap vô hạn.

## 12. Lỗi trong KEK rotation và rewrap

Khi rotate KEK, lỗi có thể xuất hiện trong thao tác unwrap DEK bằng KEK cũ hoặc wrap DEK bằng KEK mới.

| Tình huống | Hướng xử lý |
|---|---|
| KMS không unwrap được DEK cũ | Kiểm tra key version, encryption context, permission và ciphertext integrity |
| Wrap bằng KEK mới thất bại | Giữ wrapped DEK cũ; kiểm tra key state, quota và policy |
| Rewrap thành công nhưng metadata chưa cập nhật | Tra cứu kết quả, cập nhật metadata theo transaction/idempotency |
| Metadata cập nhật nhưng event thất bại | Phát lại event từ outbox/audit; không rewrap lần nữa |
| Một phần DEK đã rewrap | Lưu checkpoint theo DEK; tiếp tục phần còn lại sau khi xác minh |
| Backup chưa rewrap | Giữ KEK cũ theo retention hoặc xử lý backup theo kế hoạch |

Không xóa KEK cũ khi còn wrapped DEK, backup hoặc archive cần nó. Nếu KMS hỗ trợ native key material versioning và tự chọn version cũ khi unwrap, cần hiểu chính xác semantics trước khi khởi chạy rewrap hàng loạt.

## 13. Lỗi trong DEK rotation và re-encryption

Re-encryption có thể chạy qua hàng triệu object. Một batch có thể thất bại sau khi một phần dữ liệu đã được chuyển.

Thiết kế an toàn cần:

- Checkpoint theo object/record, không chỉ theo tổng số batch.
- Ghi metadata version cùng ciphertext bằng thao tác nguyên tử.
- Giữ ciphertext gốc cho tới khi ciphertext mới được xác minh.
- Xác minh AEAD tag hoặc integrity trước khi dùng plaintext.
- Ghi nhận object thành công, thất bại và đang xử lý.
- Retry riêng object lỗi, tránh mã hóa lại object đã hoàn tất.
- Giới hạn concurrency và bảo vệ KMS/HSM khỏi quá tải.
- Kiểm tra replica, backup, archive và dữ liệu đang được cập nhật đồng thời.

Nếu ciphertext mới được ghi nhưng metadata key version chưa cập nhật, ứng dụng có thể không giải mã được. Nếu metadata cập nhật trước ciphertext, ứng dụng có thể chọn sai key. Dùng transaction, atomic rename/object replacement hoặc manifest versioned để bảo đảm cặp ciphertext/metadata nhất quán.

Nếu tag không hợp lệ, checksum sai hoặc plaintext không khớp kiểm tra nghiệp vụ, dừng object đó và giữ nguyên bản gốc. Không bỏ qua authentication failure và không ghi đè bằng plaintext chưa được xác thực.

## 14. Lỗi trong signing key hoặc certificate rotation

Với asymmetric signing key, lỗi thường gặp là verifier chưa nhận public key mới, JWKS cache chưa refresh, certificate chain chưa được triển khai hoặc signer chuyển key trước khi consumer sẵn sàng.

Hướng xử lý:

- Xác minh key ID/kid và public key tương ứng.
- Kiểm tra JWKS publication, cache-control, cache refresh và issuer configuration.
- Kiểm tra certificate chain, SAN, validity, EKU, key usage và trust store.
- Giữ public key/certificate cũ trong thời gian chữ ký/token hợp lệ còn tồn tại.
- Chuyển signer theo canary và xác minh token/chữ ký mới.
- Không dùng private key cũ để ký mới nếu key đã compromise.

Với HMAC signing secret, lỗi phân phối có thể khiến signer và verifier dùng hai phiên bản khác nhau. Dùng key ID/version, overlap có thời hạn và audit việc cấp phát. Nếu secret cũ bị lộ, không giữ overlap theo quy trình định kỳ; chuyển sang incident response.

## 15. Lỗi audit hoặc event publication

Rotation operation và việc phát event là hai kết quả riêng. Có thể KMS đã rotate thành công nhưng event bus hoặc SIEM không nhận được notification.

Quy trình xử lý:

1. Kiểm tra KMS/HSM current state và native audit log.
2. Xác định rotation operation đã hoàn tất hay chưa.
3. Nếu hoàn tất, giữ state rotation đã xác nhận.
4. Phát lại notification từ transactional outbox hoặc audit source bằng event ID ổn định.
5. Deduplicate ở consumer.
6. Theo dõi event ingest và acknowledgement.

Không chạy rotation lần nữa chỉ vì publish event thất bại. Nếu audit sink là kiểm soát bắt buộc cho thao tác nhạy cảm, policy có thể yêu cầu pause các thao tác tiếp theo cho tới khi audit được khôi phục. Nếu cho phép buffer cục bộ, buffer phải bền vững, được bảo vệ và có cảnh báo khi đầy.

Không ghi secret, raw key bytes, plaintext hoặc wrapped key material vào event để “giúp debug”. Dùng request ID, key ID, version, error category và correlation ID.

## 16. KMS/HSM outage và quota exhaustion

Khi KMS/HSM không khả dụng:

- Pause rotation mới nếu không thể xác minh key state.
- Không tạo key ngoài KMS/HSM hoặc chuyển sang provider không được phê duyệt để né lỗi.
- Dùng health check, circuit breaker và retry có giới hạn.
- Kiểm tra endpoint, region, network, partition, session và quota.
- Nếu có DR region/cluster, chỉ failover theo runbook đã kiểm thử.
- Xác minh replica và key version mapping trước khi tiếp tục.
- Thông báo owner các key sắp quá hạn nếu outage kéo dài.

Quota exhaustion có thể do rotation job chạy quá đồng thời, rewrap batch quá lớn hoặc retry storm. Giảm concurrency, áp dụng backpressure, chia batch và ưu tiên key criticality. Không tăng quota hoặc quyền một cách tùy tiện khi chưa hiểu nguyên nhân.

Break-glass identity không thể khắc phục một KMS/HSM service outage nếu endpoint và phần cứng không hoạt động. Khả năng phục hồi cần có kiến trúc availability, replica, backup và quy trình vendor/DR riêng.

## 17. Permission denied và policy conflict

Khi KMS/HSM từ chối operation:

1. Xác minh principal/workload identity thực tế.
2. Kiểm tra key policy, IAM policy, grant, permission boundary và organization guardrail.
3. Kiểm tra key state và action có được phép không.
4. Kiểm tra context, tenant, environment và purpose.
5. Kiểm tra credential hết hạn hoặc workload identity binding.
6. Ghi nhận policy decision và request ID.

Không tự động cấp quyền admin hoặc wildcard để làm workflow tiếp tục. Nếu cần thay policy, tạo change/approval riêng và chỉ cấp action tối thiểu. Nếu lỗi là policy conflict, pause job để tránh vòng lặp request bị deny.

## 18. Key compromise trong lúc rotation

Compromise là tình huống bảo mật, không phải lỗi kỹ thuật thông thường. Nếu key bị lộ hoặc có bằng chứng principal trái phép sử dụng key:

1. Mở incident và xác định key ID/version, owner, purpose cùng phạm vi ảnh hưởng.
2. Thu hồi credential/grant liên quan và disable/revoke operation theo incident policy.
3. Không tiếp tục overlap với key bị compromise cho operation tạo dữ liệu mới.
4. Tạo key mới trong miền bảo vệ đã xác minh.
5. Chuyển consumer và policy sang key mới.
6. Đánh giá ciphertext, DEK, signature, token, certificate và backup phụ thuộc key cũ.
7. Re-encrypt, rewrap, phát hành lại token/certificate hoặc yêu cầu credential mới khi cần.
8. Theo dõi operation tiếp tục nhắm vào key cũ.
9. Bảo toàn audit evidence và điều tra đường rò rỉ.

Nếu cần giải mã hoặc xác minh dữ liệu lịch sử, có thể phải giữ một đường truy cập hạn chế với key cũ theo approval và giám sát. Điều này không đồng nghĩa cho phép key cũ tiếp tục encrypt hoặc sign dữ liệu mới.

## 19. Mất key material hoặc destruction nhầm

Nếu key material duy nhất bị hủy hoặc mất và không còn backup/replica hợp lệ, không có thuật toán nào tái tạo lại key ngẫu nhiên ban đầu từ ciphertext. Đây có thể là sự cố mất dữ liệu không thể phục hồi.

Khi nghi ngờ mất key:

- Dừng các thao tác có thể ghi đè metadata hoặc xóa thêm bản sao.
- Xác định key ID/version và trạng thái destruction từ audit source.
- Kiểm tra backup, replica, HSM cluster, recovery domain và bản escrow được phê duyệt.
- Xác minh backup thực sự chứa key material tương ứng và có thể restore.
- Không tạo key mới cùng tên rồi giả định ciphertext cũ sẽ giải mã được.
- Mở incident, đánh giá phạm vi dữ liệu và thông báo theo quy trình tổ chức.

Nếu key bị schedule deletion nhưng còn trong grace period, chỉ cancel deletion theo policy và phê duyệt phù hợp sau khi xác minh nguyên nhân. Không coi cancel deletion là bước khắc phục mặc định khi key bị compromise.

## 20. Rollback hay forward recovery?

Không phải mọi bước rotation đều có phép đảo ngược an toàn. Khi version mới đã được dùng để mã hóa dữ liệu hoặc tạo chữ ký, quay về version cũ có thể không giải quyết được dependency.

| Tình trạng | Hướng xử lý thường phù hợp |
|---|---|
| Preflight lỗi, chưa có side effect | Sửa điều kiện rồi chạy lại hoặc hủy job |
| Version mới được tạo nhưng chưa activate | Giữ ở trạng thái chưa dùng; validate hoặc cô lập theo policy |
| Activation đã xảy ra, chưa có consumer dùng version mới | Có thể chuyển lại theo quy trình nếu key cũ an toàn và KMS hỗ trợ |
| Một số consumer đã dùng version mới | Thường ưu tiên forward recovery và giữ khả năng đọc cả hai version |
| Re-encryption một phần | Resume từ checkpoint hoặc phục hồi object riêng; không xóa bản gốc |
| Event publish thất bại | Replay event; không đảo rotation |
| Key cũ bị compromise | Incident response; không rollback để bật lại key cũ |
| Key cũ đã bị destroy | Chỉ recovery nếu có backup/replica hợp lệ; nếu không có thể irrecoverable |

Forward recovery nghĩa là sửa nguyên nhân và tiếp tục từ trạng thái đã xác nhận. Compensation là một hành động mới để đưa hệ thống về trạng thái nghiệp vụ an toàn hơn; nó không nhất thiết đảo ngược side effect mật mã. Ví dụ, nếu alias đã chuyển và dữ liệu mới đã được mã hóa bằng version mới, có thể giữ cả hai version để đọc và tiếp tục migration thay vì cố đảo mọi dữ liệu.

Mọi quyết định rollback/compensation phải xem xét key compromise status, dữ liệu đã tạo, backup, consumer và policy.

## 21. Pause, quarantine và kill switch

Automation cần cơ chế dừng an toàn:

- Pause một rotation job cụ thể.
- Pause các job thuộc một key family hoặc dependency group.
- Tạm ngừng scheduler tạo job mới.
- Chặn activation/alias switch khi có incident.
- Quarantine version mới chưa được xác minh.
- Dừng batch re-encryption và giữ checkpoint.
- Ngăn destruction trong khi incident hoặc dependency review đang mở.

Kill switch phải có owner, quyền sử dụng, audit và cách resume. Không nên dùng một kill switch duy nhất có thể dừng toàn bộ hoạt động KMS cần thiết để xử lý incident. Ví dụ, pause rotation định kỳ nhưng vẫn cho phép disable key compromise theo emergency runbook.

## 22. Observability và alerting cho failure handling

Theo dõi cả lỗi kỹ thuật lẫn mức độ tiến triển:

| Metric/event | Ý nghĩa |
|---|---|
| Rotation failure rate | Tỷ lệ job thất bại theo key purpose và môi trường |
| Jobs in Paused/NeedsReview | Số workflow đang chờ xử lý |
| Ambiguous operation count | Request timeout chưa xác định kết quả |
| Retry count and age | Số lần retry và thời gian job bị kéo dài |
| KMS/HSM throttle/error rate | Tình trạng quota và service |
| Consumer migration lag | Consumer chưa chuyển version |
| Rewrap/re-encryption backlog | DEK/object còn chưa xử lý |
| Old-version operation count | Operation còn dùng key version cũ |
| Integrity verification failures | Tag, checksum hoặc signature không hợp lệ |
| Missing audit/event count | Operation không có bằng chứng hoặc event bị mất |
| Key overdue duration | Key vượt cryptoperiod trong bao lâu |

Alert nên phân biệt:

- **Critical:** key compromise, unauthorized rotation, key loss hoặc integrity failure ảnh hưởng dữ liệu quan trọng.
- **High:** production rotation thất bại, consumer migration bị kẹt, decrypt/sign failure tăng mạnh.
- **Medium:** retry vượt ngưỡng, event trễ, key quá hạn nhưng còn trong grace period.
- **Informational:** job pause có chủ đích, retry transient đã phục hồi hoặc rotation hoàn tất.

Mỗi alert cần owner, runbook, severity, correlation ID và điều kiện đóng. Tránh gửi alert lặp không giới hạn; dùng deduplication và escalation theo thời gian.

## 23. Audit record cho rotation failure

Một failure record nên ghi:

- Rotation job ID và event ID.
- Key ID, logical key ID và version liên quan.
- Actor/workload identity và trigger.
- State trước lỗi và state sau khi xác minh.
- Operation/request ID phía KMS/HSM.
- Error category, code, retryability và thời điểm.
- Side effect đã xảy ra hoặc chưa xác định.
- Consumer/data scope bị ảnh hưởng.
- Retry, pause, compensation hoặc recovery action.
- Approval, incident/change reference và người chịu trách nhiệm.
- Kết quả cuối cùng và thời điểm đóng.

Không ghi key material, secret, password, plaintext hoặc wrapped key bytes. Log phải được bảo vệ khỏi sửa đổi và lưu trong retention phù hợp. Nếu outcome chưa xác định, ghi rõ trạng thái ambiguous thay vì tự ghi failed hoặc succeeded.

## 24. Runbook xử lý rotation failure

Một runbook tổng quát:

1. **Stop unsafe progression:** pause các bước có thể tạo thêm side effect.
2. **Declare/triage:** xác định mức độ, key owner, service và incident/change ID.
3. **Read authoritative state:** truy vấn KMS/HSM, key inventory và audit source.
4. **Map side effects:** xác định version được tạo/activate, consumer đã đổi và dữ liệu đã chuyển.
5. **Classify failure:** transient, ambiguous, configuration, authorization, integrity, dependency hay compromise.
6. **Choose recovery:** retry, resume, forward recovery, compensation, rollback có kiểm soát hoặc incident response.
7. **Protect old material:** giữ version cần cho decrypt/verify; không destroy trước dependency check.
8. **Execute with approval:** dùng principal và action tối thiểu.
9. **Verify:** kiểm thử operation, consumer, dữ liệu và audit.
10. **Close:** cập nhật inventory, thu hồi quyền tạm, thông báo owner và lưu hậu kiểm.

Không bắt đầu từ giả định rằng key version mới là active hoặc key cũ vẫn an toàn. Mọi quyết định phải dựa trên state đã xác minh.

## 25. Ví dụ: timeout sau khi tạo KEK version

Giả sử rotation orchestrator gọi KMS tạo KEK version mới. Request timeout và worker không nhận được response.

1. Job được chuyển sang NeedsReconciliation, không gửi create request mới.
2. Orchestrator tra cứu theo idempotency token/request ID.
3. KMS audit xác nhận version mới đã được tạo nhưng chưa active.
4. Worker kiểm tra key type, algorithm, size, purpose và policy.
5. Nếu thuộc tính đạt, workflow lưu version ID và tiếp tục activation theo approval.
6. Nếu thuộc tính sai, giữ version ở trạng thái không sử dụng và mở review.
7. Khi activation hoàn tất, workflow chuyển consumer/re-wrap theo semantics KMS.
8. Chỉ sau verify mới đánh dấu phase tương ứng Completed.

Nếu KMS không cung cấp cách tra cứu operation và kết quả vẫn không rõ, job phải giữ trạng thái NeedsReview. Tạo thêm version có thể gây rác tài nguyên hoặc làm workflow không xác định được version nào là kết quả chính.

## 26. Ví dụ: re-encryption thất bại giữa batch

Một service chuyển 100.000 object từ DEK cũ sang DEK mới. Sau 40.000 object, worker mất kết nối storage.

1. Dừng batch mới và giữ checkpoint theo object.
2. Đối chiếu object đã commit ciphertext mới với metadata key version.
3. Xác minh các object đang xử lý có trạng thái nguyên tử hay không.
4. Kiểm tra object chưa commit vẫn giữ ciphertext gốc.
5. Chạy integrity/decrypt test trên mẫu của batch đã hoàn tất.
6. Khôi phục storage connection và quota KMS/HSM.
7. Resume từ object chưa hoàn tất; không mã hóa lại object đã commit nếu idempotency không yêu cầu.
8. Theo dõi số lượng, checksum và lỗi từng object.
9. Chỉ retire DEK cũ khi toàn bộ object, replica, backup và archive đã được kiểm tra.

Nếu phát hiện object mới không giải mã được hoặc authentication tag sai, dừng migration và mở incident. Không xóa bản gốc hoặc tiếp tục batch để che lấp lỗi.

## 27. Ví dụ: key compromise trong lúc rotation định kỳ

Một scheduler đang chuẩn bị rotate signing key theo lịch thì SIEM phát hiện principal trái phép gọi sign bằng key hiện tại.

1. Dừng rotation định kỳ đang chạy để tránh overlap tự động.
2. Mở incident và xác định key, principal, thời điểm cùng token/chữ ký bị ảnh hưởng.
3. Thu hồi credential/grant của principal bị nghi ngờ.
4. Disable quyền sign bằng key cũ theo incident policy; giữ verify lịch sử nếu cần và an toàn.
5. Tạo signing key mới trong HSM/KMS đã xác minh.
6. Công bố public key mới hoặc phân phối secret version mới theo kênh tin cậy.
7. Chuyển signer và verifier; thu hồi token/certificate liên quan nếu cần.
8. Theo dõi request tiếp tục dùng key cũ và các lỗi verify.
9. Điều tra nguồn compromise, bảo toàn audit và thực hiện hậu kiểm.

Không dùng overlap rotation thông thường để tiếp tục ký bằng key bị nghi ngờ compromise. Nếu cần xác minh chữ ký cũ, tách quyền verify khỏi quyền sign trong phạm vi nền tảng hỗ trợ; với HMAC, hai quyền dùng chung secret nên cần kiểm soát đặc biệt.

## 28. Những sai lầm thường gặp

- **Retry mọi lỗi:** permission hoặc invalid state tạo retry storm mà không khắc phục nguyên nhân.
- **Retry create sau timeout:** tạo nhiều key version do operation đầu có thể đã thành công.
- **Đánh dấu Failed khi outcome chưa rõ:** inventory không phản ánh trạng thái KMS/HSM.
- **Đánh dấu Completed khi chỉ tạo version:** consumer và dữ liệu có thể chưa chuyển.
- **Rollback bằng cách bật key cũ:** có thể khôi phục key đã compromise hoặc làm dữ liệu mới không đọc được.
- **Xóa key cũ ngay khi có lỗi:** làm mất khả năng decrypt dữ liệu lịch sử.
- **Tiếp tục re-encryption sau tag failure:** có thể chấp nhận dữ liệu đã bị sửa.
- **Không checkpoint từng object:** không thể resume an toàn sau batch failure.
- **Để worker cũ ghi đè state:** thiếu fencing/generation control.
- **Gộp rotation failure với event delivery failure:** chạy rotation lần hai chỉ vì notification bị mất.
- **Cấp admin rộng để xử lý permission denied:** mở rộng blast radius và che lỗi policy.
- **Không pause scheduler:** tạo thêm job trong khi incident chưa được xử lý.
- **Không phân biệt outage và compromise:** enable key bị disable vì incident.
- **Không test restore:** không biết recovery path có thực sự hoạt động.

## 29. Checklist rotation failure handling

- [ ] Workflow có state machine bền vững và lưu checkpoint sau side effect.
- [ ] Phân loại lỗi transient, ambiguous, permanent, authorization, integrity và compromise.
- [ ] Timeout được reconciliation bằng request/idempotency reference trước khi retry.
- [ ] Retry có backoff, jitter, retry budget và circuit breaker.
- [ ] Có lock/lease, fencing token và protection khỏi concurrent workflow.
- [ ] Key state được đọc từ KMS/HSM hoặc nguồn có thẩm quyền.
- [ ] Version mới chưa được xác minh không được activate.
- [ ] Consumer migration có thể pause/resume và theo dõi riêng.
- [ ] Rewrap/re-encryption có checkpoint, atomic metadata và integrity verification.
- [ ] Ciphertext gốc và key version cũ được giữ theo dependency/retention.
- [ ] Audit/event failure được tách khỏi rotation operation result.
- [ ] Permission denied không tự động dẫn tới cấp quyền rộng.
- [ ] Key compromise dùng incident response, không rollback mù.
- [ ] Key loss/destruction được xử lý như incident về khả năng phục hồi dữ liệu.
- [ ] Có pause/kill switch với owner và audit.
- [ ] Alert có severity, owner, runbook và escalation.
- [ ] Đã diễn tập timeout, partial migration, KMS outage, event loss và restore.

Rotation failure handling bảo đảm workflow không tiếp tục một cách mù quáng khi trạng thái key hoặc dữ liệu chưa rõ. Cần phân loại lỗi, xác minh trạng thái KMS/HSM, retry có idempotency, lưu checkpoint và giữ version cũ khi còn dependency. Khi có side effect không thể đảo ngược, forward recovery thường an toàn hơn rollback; khi key bị compromise hoặc mất, phải chuyển sang incident response và đánh giá tác động dữ liệu. Audit, monitoring và diễn tập recovery giúp tổ chức xử lý lỗi mà vẫn giữ được tính toàn vẹn, khả năng giải mã và trách nhiệm vận hành.
