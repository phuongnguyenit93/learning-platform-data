# Giám sát hạn mức, tài nguyên mồ côi và lỗi đối soát

Service broker không chỉ cần biết một request provision đã trả về thành công hay chưa. Broker còn phải biết tenant đã dùng bao nhiêu tài nguyên, quota còn lại bao nhiêu, provider đang giữ những resource nào và trạng thái thực tế có còn khớp với dữ liệu broker lưu hay không. Nếu chỉ theo dõi HTTP response và operation status, broker có thể bỏ sót database bị tạo dở, volume không được xóa, binding credential còn tồn tại hoặc quota bị giữ sau khi thao tác thất bại.

Trong module SPRING_CLOUD_SERVICE_BROKER, giám sát hạn mức và đối soát cần nối ba góc nhìn: **usage/quota trong broker**, **desired state của service instance/binding**, và **actual inventory từ cloud provider**. Reconciliation phát hiện sai lệch giữa các góc nhìn này, phân loại tài nguyên mồ côi và đưa ra hành động phục hồi có kiểm soát. Mục tiêu là tìm ra rò rỉ tài nguyên và sai lệch sớm, giữ accounting chính xác và tránh tự động xóa nhầm tài nguyên hợp lệ.

## 1. Ba loại dữ liệu cần giám sát

Một broker thường quản lý ba nhóm dữ liệu liên quan nhưng không thể thay thế cho nhau:

| Nhóm | Nguồn chính | Câu hỏi cần trả lời |
|---|---|---|
| Quota và usage | Broker state store, quota ledger, reservation records | Tenant đã được cấp bao nhiêu, đã reserve bao nhiêu và còn bao nhiêu khả năng? |
| Desired state | Service instance, binding, operation và ownership metadata trong broker | Broker dự định tài nguyên nào tồn tại, với plan/cấu hình/trạng thái nào? |
| Actual inventory | API/listing của provider, Kubernetes hoặc cloud control plane | Provider thực sự đang giữ những resource nào và trạng thái của chúng ra sao? |

Ví dụ, broker có thể lưu instance inst-42 ở trạng thái ACTIVE và ghi nhận storage 100 GB. Provider inventory lại có hai volume cùng gắn tag instance inst-42, tổng dung lượng 200 GB. Usage ledger có thể vẫn chỉ ghi 100 GB. Nếu chỉ xem broker database, broker không phát hiện được resource thừa. Nếu chỉ xem provider, broker có thể không biết resource nào được tạo hợp lệ và resource nào là rò rỉ.

Mỗi nguồn phải có định danh và thời điểm quan sát. Inventory snapshot lúc 10:00 không nhất thiết phản ánh trạng thái provider tại 10:05. Dashboard cần hiển thị độ mới của dữ liệu để operator không nhầm snapshot cũ với trạng thái tức thời.

## 2. Xác định quota theo loại tài nguyên

Quota không chỉ là số lượng service instance. Tùy service và plan, broker có thể quản lý:

- Số service instance của mỗi tenant.
- Tổng storage, memory, CPU hoặc số replica.
- Số binding hoặc database principal.
- Số endpoint, route hoặc network attachment.
- Số operation đang chạy đồng thời.
- Số lần gọi provider trong một khoảng thời gian.
- Số snapshot, backup hoặc dung lượng backup.

Quota nên được định nghĩa theo scope rõ ràng: tenant, service, plan, region, provider account hoặc toàn broker. Ví dụ tenant A có giới hạn 10 instance PostgreSQL, 2 TB storage và 20 binding; giới hạn toàn provider có thể là 500 instance và 100 operation đồng thời.

| Loại quota | Đơn vị | Scope ví dụ | Cách tính |
|---|---|---|---|
| Instance count | instance | Tenant + service | Instance đang được tính quota |
| Storage | GB | Tenant + plan | Tổng dung lượng đã commit và reservation |
| Replica | replica | Instance/tenant | Desired replicas theo cấu hình |
| Binding | binding | Instance | Binding active và reservation đang tạo |
| Concurrent operation | operation | Provider/tenant | Operation đang giữ slot xử lý |
| API rate | request/window | Provider account | Số request provider trong cửa sổ thời gian |

Không cộng các đơn vị không tương thích vào cùng một quota. Cũng không mặc định mọi trạng thái instance đều tiêu thụ quota giống nhau. Ví dụ, instance PROVISIONING có thể đã giữ reservation; instance DEPROVISIONING có thể vẫn tiêu thụ storage cho tới khi provider xác nhận xóa.

## 3. Tách reserved, committed và observed usage

Một phép tính quota dễ hiểu cần phân biệt:

- **Reserved usage:** quota đã giữ cho operation đang chạy nhưng tài nguyên chưa được xác nhận hoàn tất.
- **Committed usage:** quota của tài nguyên broker đã xác nhận và đang quản lý.
- **Observed usage:** mức sử dụng thực tế được provider báo về qua inventory hoặc metrics.

Ví dụ một tenant có quota storage 500 GB:

| Thành phần | Dung lượng |
|---|---:|
| Hai instance ACTIVE | 200 GB |
| Một provision đang chạy, đã reserve | 100 GB |
| Reservation còn lại | 0 GB |
| Tổng quota được tính | 300 GB |
| Provider inventory quan sát | 310 GB |

Khoảng chênh 10 GB có thể do volume tạm, snapshot, metadata overhead hoặc resource mồ côi. Cần phân loại theo mô hình billing/quota của service thay vì tự động cộng hoặc bỏ qua mọi resource phụ.

Quota usage được tính bằng committed usage cộng active reservations. Observed usage là phép đo đối chiếu riêng. Nếu provider có resource phụ tiêu thụ quota, policy cần quy định rõ chúng được tính vào quota nào.

## 4. Reservation và cập nhật quota an toàn

Quota phải được reserve nguyên tử trước khi bắt đầu tác dụng phụ có thể tạo tài nguyên. Nếu hai request đồng thời cùng đọc quota còn 100 GB rồi mỗi request reserve 80 GB, tổng reservation có thể vượt giới hạn nếu không có transaction/atomic counter.

Luồng reservation:

1. Xác định tenant, service, plan và mức tài nguyên yêu cầu sau validation.
2. Trong transaction, khóa hoặc cập nhật atomic quota ledger.
3. Kiểm tra committed + reserved + requested không vượt limit.
4. Ghi reservation gắn với operation ID.
5. Commit rồi mới dispatch worker.
6. Khi provision thành công, chuyển reservation thành committed usage.
7. Khi thất bại hoàn toàn, giải phóng reservation.
8. Khi deprovision thành công, giảm committed usage theo resource thực sự đã được thu hồi.

Không release quota chỉ vì HTTP request timeout. Worker có thể đã tạo resource ở provider nhưng chưa ghi kết quả. Cần reconcile operation trước khi quyết định release reservation.

Ví dụ pseudocode:

~~~java
@Transactional
public QuotaReservation reserve(
        String tenantId,
        String operationId,
        ResourceRequest request) {

    QuotaAccount account = quotaRepository.lockByTenant(tenantId);
    QuotaAmount required = quotaPolicy.calculate(request);

    if (!account.canReserve(required)) {
        throw new QuotaExceededException();
    }

    account.reserve(required);
    quotaRepository.save(account);
    reservationRepository.insert(
            tenantId, operationId, required, ReservationStatus.ACTIVE);

    return new QuotaReservation(operationId, required);
}
~~~

Đây là pseudocode; kiểu QuotaAmount, repository và transaction manager thuộc ứng dụng. Cần có unique constraint cho operation ID để request retry không tạo reservation thứ hai. Nếu ledger và operation nằm cùng database, có thể ghi chúng trong một transaction.

## 5. Vòng đời reservation và reservation bị kẹt

Reservation nên có trạng thái rõ ràng:

| Trạng thái | Ý nghĩa | Quota accounting |
|---|---|---|
| ACTIVE | Đã giữ quota cho operation đang xử lý | Tính vào reserved usage |
| COMMITTED | Tài nguyên đã được xác nhận | Chuyển sang committed usage |
| RELEASED | Operation thất bại hoặc đã được bù trừ an toàn | Không còn tính |
| EXPIRED_PENDING_REVIEW | Quá thời gian dự kiến nhưng chưa rõ provider outcome | Tiếp tục giữ hoặc quarantine theo policy |

Không đặt TTL rồi xóa reservation đang ACTIVE một cách tự động. Operation có thể đang chạy lâu hoặc worker đang phục hồi sau outage. Reservation quá hạn cần được phát hiện, đối chiếu với operation và provider inventory trước khi release.

Một cảnh báo hữu ích là tuổi reservation ACTIVE lớn hơn ngưỡng theo operation type. Ví dụ provision thông thường kéo dài vài phút, nhưng ngưỡng cụ thể phải dựa trên SLA và phân phối thời gian thực tế. Deprovision backup-heavy có thể cần thời gian dài hơn.

## 6. Tài nguyên mồ côi là gì?

Tài nguyên mồ côi (orphan resource) là tài nguyên tồn tại ở provider nhưng không còn được broker quản lý bởi một instance, binding hoặc operation hợp lệ. Một vài trường hợp:

- Database đã tạo thành công nhưng broker chết trước khi lưu provider resource ID.
- Volume vẫn tồn tại sau khi deprovision thất bại giữa chừng.
- Binding principal hoặc secret chưa được revoke sau khi unbind.
- Snapshot tạm không được xóa sau khi update/migration.
- Resource còn tag instance ID đã bị xóa hoặc không còn trong broker database.
- Resource được tạo thủ công hoặc bởi một hệ thống khác nhưng vô tình trùng naming convention của broker.

Không phải mọi resource không có record khớp đều là orphan. Có thể inventory API chưa đồng bộ, record đang được tạo, operation chưa commit, tag thiếu hoặc resource thuộc một broker deployment khác. Vì vậy, orphan detection cần nhiều tín hiệu và trạng thái suspected orphan trước khi có kết luận.

## 7. Phân loại orphan và drift

Đối soát nên phân biệt ít nhất các dạng sai lệch:

| Loại sai lệch | Broker state | Provider inventory | Hướng xử lý |
|---|---|---|---|
| Orphan candidate | Không có owner/operation hợp lệ | Resource tồn tại | Xác minh ownership và tuổi trước khi quarantine |
| Missing resource | Instance ACTIVE | Resource không tồn tại | Kiểm tra provider outage/deletion ngoài luồng; reconcile instance |
| Duplicate resource | Một resource được mong đợi | Nhiều resource cùng ownership | Xác định resource chính và xử lý phần thừa có kiểm soát |
| Configuration drift | Plan/size mong đợi A | Provider thực tế B | So sánh desired/actual và quyết định sửa hoặc cập nhật broker state |
| Stale broker record | Broker giữ instance/binding | Provider xác nhận resource đã mất | Đánh dấu drift, phục hồi hoặc cập nhật state theo policy |
| Stuck transitional state | Operation/instance còn PENDING/RUNNING | Provider đã đạt trạng thái cuối | Reconcile operation và hoàn tất state transition |
| Untracked child resource | Instance còn hợp lệ | Volume/snapshot/principal không được ghi nhận | Liên kết lại nếu xác minh được, nếu không thì quarantine |

Orphan detection và quota reconciliation có liên hệ nhưng không đồng nhất. Một volume thừa có thể làm observed usage vượt quota; một reservation kẹt có thể làm broker báo hết quota dù provider không có resource nào tương ứng.

## 8. Ownership metadata để đối chiếu

Mỗi resource do broker tạo nên mang metadata đủ để xác định nguồn gốc và chủ sở hữu, nếu provider hỗ trợ tags/labels:

- managed-by: định danh broker deployment hoặc controller.
- broker-id: định danh broker/service.
- tenant-ref: mã tham chiếu tenant đã được bảo vệ.
- instance-id: service instance ID.
- binding-id: binding ID nếu resource thuộc binding.
- operation-id: operation đã tạo hoặc thay đổi resource.
- resource-kind: database, volume, snapshot, principal...
- created-at hoặc generation/version nếu cần.

Không đưa password, token, thông tin cá nhân hoặc parameters nhạy cảm vào tag. Tag có thể hiển thị cho nhiều operator và thường được provider lưu trong inventory/log.

Tên resource không đủ làm ownership proof. Hai tenant có thể dùng cùng tên database; một resource có thể được import hoặc tạo thủ công. Hãy kết hợp provider account/project, region, resource ID, broker marker và instance reference.

Nếu provider không hỗ trợ tags, duy trì mapping bền vững trong broker và tận dụng external resource ID. Khi broker mất mapping do lỗi, không tự nhận quyền sở hữu một resource chỉ dựa trên tên gần giống.

## 9. Reconciliation loop

Reconciliation là vòng lặp định kỳ so sánh desired state với actual state, sau đó sửa hoặc ghi nhận sai lệch. Một vòng lặp an toàn:

1. Lấy batch instance/operation cần kiểm tra.
2. Lấy provider inventory theo account/project/region với pagination.
3. Chuẩn hóa resource type, ID, status, tags và observed timestamp.
4. Match provider resource với broker record bằng external ID và ownership metadata.
5. Phân loại missing, orphan candidate, duplicate, drift hoặc transitional state.
6. Ghi reconciliation finding với evidence và lần quan sát.
7. Chạy remediation tự động chỉ với trường hợp policy cho phép; còn lại tạo alert/case để operator xem.
8. Ghi kết quả, retry metadata và metric.

Không chạy một vòng quét không giới hạn trên toàn bộ provider inventory trong request HTTP. Dùng background job, batch nhỏ, cursor và giới hạn concurrency. Với account lớn, chia theo provider account, region hoặc resource type.

## 10. Đối soát eventual consistency

Cloud provider có thể trả thành công trước khi resource xuất hiện trong list API, hoặc trả delete accepted trước khi resource biến mất hoàn toàn. Kubernetes controller cũng có thể mất thời gian để converge desired state.

Vì vậy, một lần quan sát không đủ để kết luận orphan hoặc missing resource:

- Dùng grace period sau provision/update/deprovision.
- Lưu observed_at và provider request/operation reference.
- Retry inventory read khi provider trả lỗi transient.
- Xác nhận qua nhiều lần scan hoặc truy vấn resource trực tiếp trước remediation.
- Phân biệt NOT_FOUND chắc chắn với timeout/permission error.
- Không xem inventory API unavailable là bằng chứng resource đã mất.

Ví dụ, một volume mới provision được 30 giây nhưng chưa xuất hiện trong list API. Nếu broker đánh dấu missing ngay và chạy compensation, nó có thể xóa hoặc rollback một thao tác đang hoàn tất. Grace period nên theo provider semantics và được cấu hình theo resource type.

## 11. Phân loại finding trước khi sửa

Một reconciliation finding nên lưu:

| Field | Mục đích |
|---|---|
| finding_id | Định danh lần phát hiện |
| resource_ref | Provider account/region/resource ID |
| broker_instance_id | Instance liên quan nếu xác định được |
| finding_type | ORPHAN_CANDIDATE, MISSING, DUPLICATE, DRIFT... |
| confidence | Mức độ chắc chắn của kết quả |
| evidence | Các dấu hiệu đã so sánh, không chứa secret |
| first_seen_at | Lần đầu phát hiện |
| last_seen_at | Lần gần nhất còn quan sát |
| status | OPEN, VERIFYING, QUARANTINED, REMEDIATING, RESOLVED |
| remediation_id | Tham chiếu hành động nếu có |

Tách finding khỏi operation. Finding là kết quả giám sát; remediation là một workflow riêng có thể được audit và retry. Không dùng một cờ orphan=true trên resource làm nơi lưu toàn bộ lịch sử đối soát.

## 12. Remediation an toàn

Không tự động xóa mọi resource bị nghi là orphan. Một lỗi match hoặc một inventory snapshot cũ có thể khiến broker xóa tài nguyên của tenant khác hoặc resource đang được hệ thống ngoài quản lý.

Các mức xử lý:

1. **Observe:** chỉ ghi finding và metric.
2. **Verify:** truy vấn trực tiếp provider, kiểm tra ownership, age và operation history.
3. **Quarantine:** gắn nhãn/đưa vào danh sách cần xem xét; nếu provider hỗ trợ, ngăn cấp phát mới hoặc hạn chế sử dụng mà không xóa.
4. **Remediate:** chạy cleanup theo policy đã được phê duyệt, có idempotency key và audit record.
5. **Resolve:** xác minh resource đã được xử lý và finding đóng.

Tự động remediation chỉ phù hợp khi ownership chắc chắn, không còn operation active, resource vượt grace period, không có dependency còn dùng và hành động có thể lặp an toàn. Các resource không rõ owner, có dữ liệu khách hàng hoặc có ràng buộc backup nên yêu cầu operator approval theo quy trình của hệ thống.

Cleanup action cần có operation ID riêng, trạng thái, attempt, timeout, audit trail và kết quả cuối. Không xóa trực tiếp từ reconciliation scanner bằng một lệnh provider không có record theo dõi.

## 13. Đối soát quota với provider inventory

Quota ledger là nguồn có thẩm quyền cho quyết định admission vì nó cần hỗ trợ reservation nguyên tử. Provider inventory là nguồn quan sát để phát hiện sai lệch và resource usage thực tế.

Định kỳ so sánh:

- Broker committed usage với tổng resource được xác minh thuộc broker.
- Active reservations với operation còn hợp lệ.
- Binding count với số principal/credential resource thực tế.
- Storage/replica desired values với provider configuration.
- Resource đã xóa ở provider nhưng vẫn còn committed usage.
- Resource tồn tại ở provider nhưng không có broker owner.

Không tự ghi đè quota ledger bằng tổng provider inventory một cách mù quáng. Inventory có thể chứa resource do operator hoặc hệ thống khác tạo. Trước khi điều chỉnh usage, cần match ownership và loại trừ resource phụ không tính quota.

Một quy trình reconcile quota:

1. Tạo snapshot usage theo tenant/service/plan.
2. Tạo snapshot provider inventory đã lọc theo broker ownership.
3. Tính chênh lệch theo đơn vị tương thích.
4. Phân loại nguyên nhân: reservation stale, orphan, missing, duplicate hoặc drift.
5. Ghi adjustment ledger có tham chiếu finding/remediation.
6. Cập nhật metric và cảnh báo.

Adjustment phải có audit record, actor/reason và idempotency key. Không sửa trực tiếp con số committed usage mà không có lịch sử giải thích.

## 14. Metrics cho quota và reconciliation

Một bộ metric hữu ích có thể gồm:

| Metric | Ý nghĩa | Label nên dùng |
|---|---|---|
| broker_quota_limit | Quota limit | service, resource_type, scope_tier |
| broker_quota_committed | Usage đã commit | service, resource_type |
| broker_quota_reserved | Usage đang reserve | service, resource_type |
| broker_quota_rejections_total | Số request bị từ chối vì quota | service, plan, reason |
| broker_orphan_candidates | Số orphan candidate đang mở | provider, resource_type, finding_type |
| broker_reconciliation_findings | Finding theo trạng thái | provider, finding_type, status |
| broker_reconciliation_last_success_timestamp | Lần đối soát thành công cuối | provider, region |
| broker_reconciliation_duration_seconds | Thời gian một vòng đối soát | provider, resource_type |
| broker_reconciliation_errors_total | Lỗi gọi inventory hoặc reconcile | provider, operation |
| broker_reservation_age_seconds | Tuổi reservation active | operation_type |
| broker_inventory_observed_timestamp | Thời điểm snapshot inventory | provider, region |

Không dùng tenant ID, instance ID, binding ID hoặc resource ID làm metric label có cardinality không giới hạn. Các định danh đó có thể đặt trong log/tracing hoặc bảng finding có quyền truy cập kiểm soát.

## 15. Dashboard vận hành

Dashboard nên giúp operator trả lời nhanh:

- Tenant/service nào đang gần hết quota?
- Bao nhiêu quota đang committed và bao nhiêu đang reserved?
- Reservation nào đã tồn tại lâu hơn ngưỡng?
- Có bao nhiêu orphan candidate theo provider và resource type?
- Finding nào lặp lại qua nhiều lần scan?
- Lần reconciliation thành công gần nhất là khi nào?
- Provider inventory hiện có mới hay đã stale?
- Có missing resource hoặc duplicate resource nào ảnh hưởng instance ACTIVE?
- Cleanup/remediation nào đang chạy, thất bại hoặc chờ phê duyệt?

Một bảng tổng quan:

| Panel | Nội dung | Dùng để |
|---|---|---|
| Quota headroom | Limit, committed, reserved, remaining | Phát hiện gần cạn quota |
| Reservation aging | Tuổi và trạng thái reservation | Tìm operation kẹt |
| Inventory coverage | Resource được match/unknown/missing | Đánh giá chất lượng đối soát |
| Orphan findings | Finding theo tuổi, confidence, owner scope | Ưu tiên điều tra |
| Drift | Desired vs actual plan/size/state | Phát hiện cấu hình sai lệch |
| Reconciliation health | Last success, duration, errors, backlog | Phát hiện scanner hoặc provider API gặp lỗi |
| Remediation status | Pending, running, failed, resolved | Theo dõi cleanup an toàn |

Luôn hiển thị last_success và observed_at. Một dashboard xanh dựa trên inventory snapshot cũ không phải tín hiệu hệ thống đang khỏe.

## 16. Alert và ngưỡng cảnh báo

Ngưỡng phải dựa trên baseline, quota contract và SLA. Ví dụ:

- Quota headroom dưới mức cảnh báo hoặc dự báo sẽ cạn trước thời gian cần mở rộng capacity.
- Reservation ACTIVE vượt thời gian bình thường theo operation type.
- Orphan candidate tồn tại qua nhiều lần scan và vượt grace period.
- Instance ACTIVE nhưng provider resource bị missing qua nhiều lần xác minh.
- Reconciliation không có lần thành công mới trong khoảng thời gian cho phép.
- Tỷ lệ inventory API lỗi hoặc thời gian scan tăng đột biến.
- Remediation thất bại hoặc bị lặp quá số lần cho phép.
- Usage ledger và observed inventory chênh lệch vượt tolerance đã định nghĩa.

Không cảnh báo chỉ dựa trên một giá trị tuyệt đối giống nhau cho mọi plan. Một tenant quota 10 GB và một tenant quota 10 TB có quy mô khác nhau. Có thể kết hợp phần trăm quota, lượng tuyệt đối và tốc độ tăng usage.

Alert nên có finding ID hoặc link tới dashboard/query, provider account/region đã được che phù hợp, loại resource và hướng điều tra. Không đưa credentials hoặc thông tin nhạy cảm vào notification.

## 17. Bảo vệ API provider và dữ liệu giám sát

Reconciliation có thể tạo nhiều API call để list/describe resource. Cần:

- Dùng credential read-only cho inventory scan khi có thể.
- Dùng quyền cleanup riêng cho remediation worker.
- Phân tách provider account/project theo tenant hoặc môi trường.
- Giới hạn pagination, concurrency và API rate.
- Dùng backoff khi provider rate limit hoặc unavailable.
- Không log secret, raw provider response hoặc customer data không cần thiết.
- Mã hóa finding/evidence nếu có resource metadata nhạy cảm.
- Giới hạn quyền truy cập dashboard và audit trail.

Scanner chỉ cần quyền đọc inventory không nên có quyền xóa resource. Tách role giúp giảm tác động khi logic phát hiện orphan có lỗi. Remediation service phải xác minh ownership lần cuối trước khi gọi delete.

## 18. Kiểm thử quota và reconciliation

Test cần bao phủ cả accounting lẫn provider drift:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Hai request reserve cùng lúc vượt quota | Chỉ reservation hợp lệ được commit |
| Retry cùng operation ID | Không tạo reservation trùng |
| Provision thành công | Reservation chuyển thành committed usage đúng một lần |
| Provision thất bại chắc chắn | Reservation được release |
| Backend timeout sau side effect | Giữ reservation đến khi reconcile xác định kết quả |
| Deprovision accepted nhưng provider chưa xóa | Chưa release committed usage nếu policy tính resource đang tồn tại |
| Provider inventory có resource hợp lệ | Match theo external ID/ownership metadata |
| Resource không có broker owner | Tạo orphan candidate, không xóa ngay |
| Resource mới chưa xuất hiện do eventual consistency | Grace period ngăn false positive |
| Instance ACTIVE nhưng provider resource missing | Finding MISSING, không tự giả định success |
| Provider inventory API unavailable | Đánh dấu scan lỗi/stale, không tạo hàng loạt orphan |
| Hai scanner cùng chạy | Claim/partition ngăn duplicate finding hoặc remediation |
| Resource thuộc broker deployment khác | Không nhận nhầm owner |
| Remediation chạy lặp | Idempotent, không xóa nhầm resource khác |
| Quota adjustment | Có audit reference và áp dụng đúng một lần |

Nên dùng fake provider inventory có thể điều khiển thời điểm resource xuất hiện/mất đi, pagination, timeout, duplicate response và eventual consistency. Integration test với provider sandbox có thể xác nhận tag/ownership mapping nhưng không cần chạy cleanup destructive trong môi trường production.

## 19. Ví dụ luồng reconciliation

Một reconciliation job có thể được chia thành các bước rõ ràng:

~~~java
public Mono<ReconciliationSummary> reconcile(
        ProviderScope scope) {

    return inventoryClient.listAll(scope)
            .collectList()
            .flatMap(inventory ->
                    brokerStateRepository.loadManagedResources(scope)
                            .collectList()
                            .map(managed -> matcher.compare(
                                    managed, inventory)))
            .flatMap(findings ->
                    findingRepository.upsert(findings)
                            .thenReturn(summaryOf(findings)));
}
~~~

Đây là pseudocode minh họa cho một scope nhỏ. Với inventory lớn, không nên collect toàn bộ dữ liệu vào bộ nhớ; dùng pagination, streaming, partition hoặc external sort/join phù hợp. upsert cần idempotent theo resource reference + finding type + trạng thái quan sát để mỗi lần scan không tạo vô hạn finding trùng.

Remediation nên là pipeline riêng:

~~~java
public Mono<RemediationResult> remediate(
        ReconciliationFinding finding) {

    return ownershipVerifier.verify(finding)
            .filter(OwnershipProof::isCertain)
            .switchIfEmpty(Mono.error(
                    new ManualReviewRequiredException()))
            .flatMap(proof -> remediationService.execute(
                    finding, proof));
}
~~~

Trước khi xóa resource, ownershipVerifier phải kiểm tra broker marker, provider account, external resource ID, không có operation active và grace period đã qua. Nếu bằng chứng không đủ, dừng ở manual review. Không để matcher trực tiếp gọi provider delete.

## 20. Những sai lầm thường gặp

- Chỉ giám sát quota limit mà không tách reserved và committed usage.
- Release reservation ngay khi HTTP timeout.
- Dùng provider inventory làm quota ledger mà không xác minh ownership.
- Coi mọi resource không match là orphan và xóa tự động.
- Không có grace period cho eventual consistency.
- Nhầm provider API timeout với resource NOT_FOUND.
- Dùng tên resource thay cho external ID và ownership metadata.
- Chạy cleanup từ cùng scanner chỉ đọc inventory.
- Không giới hạn pagination/concurrency nên reconciliation làm provider quá tải.
- Ghi đè quota usage mà không có adjustment ledger/audit.
- Dùng tenant/instance/resource ID làm metric label có cardinality cao.
- Không hiển thị thời điểm snapshot nên operator tin dữ liệu stale.
- Không kiểm tra operation active trước khi remediation.
- Không kiểm thử worker restart hoặc hai scanner cùng chạy.

## Kết luận

Giám sát hạn mức, tài nguyên mồ côi và lỗi đối soát cần kết hợp quota ledger, desired state của broker và actual inventory từ provider. Tách reserved, committed và observed usage giúp admission control chính xác; ownership metadata và reconciliation loop giúp tìm resource missing, duplicate, orphan candidate và configuration drift. Vì provider có eventual consistency, finding phải có evidence, grace period và mức độ chắc chắn trước khi remediation. Cleanup cần workflow riêng, idempotent, audit được và chỉ chạy khi ownership đã xác minh. Metrics về quota headroom, reservation age, inventory freshness, finding backlog và reconciliation health giúp operator phát hiện rò rỉ tài nguyên sớm mà vẫn tránh xóa nhầm tài nguyên hợp lệ.
