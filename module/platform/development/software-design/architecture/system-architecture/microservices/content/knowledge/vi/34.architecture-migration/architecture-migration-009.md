# Tiêu chí chuyển hẳn, quay lui và ngừng thành phần cũ

**Nhóm kiến thức:** Chuyển đổi kiến trúc trong Software Design, System Architecture và Microservices.

Một dự án chuyển đổi kiến trúc không kết thúc khi dịch vụ mới đã chạy, bản release mới đã deploy hoặc traffic đã được chuyển sang hệ thống mới. Nó chỉ hoàn tất khi tổ chức có đủ bằng chứng để **chuyển hẳn (cutover), duy trì vận hành ổn định, quay lui hoặc chuyển tiếp khi cần, và ngừng thành phần cũ một cách an toàn**. Nếu không có tiêu chí rõ ràng, hai hệ thống có thể cùng tồn tại nhiều năm, dữ liệu bị ghi ở hai nơi, đội vận hành phải duy trì hai bộ pipeline, hoặc một lần rollback vô tình làm mất giao dịch đã phát sinh sau cutover.

Các quyết định này có liên hệ chặt chẽ nhưng không đồng nghĩa:
- **Cutover:** chuyển trách nhiệm phục vụ một luồng nghiệp vụ hoặc nhóm traffic sang đích mới.
- **Rollback:** quay về trạng thái/phiên bản trước khi một thay đổi gây lỗi, trong giới hạn dữ liệu và hợp đồng còn tương thích.
- **Roll-forward:** sửa tiếp trên hệ thống mới để phục hồi, khi quay lui không còn an toàn hoặc không còn khả thi.
- **Decommission:** ngừng, xóa hoặc thu hồi thành phần cũ sau khi đã chứng minh không còn trách nhiệm đang hoạt động.
- **Retirement:** kết thúc vòng đời một capability, API, dữ liệu hoặc hệ thống theo chính sách hỗ trợ, lưu trữ và tuân thủ.

Bài học này xây dựng tiêu chí ra quyết định dựa trên **user impact, tính đúng dữ liệu, SLO, khả năng tương thích, khả năng phục hồi, bảo mật, quyền sở hữu và chi phí vận hành**. Nội dung áp dụng cho chuyển monolith sang microservices, thay database, thay message broker, chuyển API version, di chuyển cloud, đổi nền tảng runtime và thay thế hệ thống legacy.

## 1. Chuyển đổi hoàn tất nghĩa là gì?

Một hệ thống mới có thể deploy thành công nhưng chưa đủ điều kiện thay thế hệ thống cũ. Cần phân biệt các trạng thái:

| Trạng thái | Ý nghĩa | Bằng chứng cần có |
|---|---|---|
| Built | Artifact mới được tạo | Build, scan, provenance |
| Deployed | Thành phần mới đã chạy | Readiness, version, config |
| Integrated | Các dependency kết nối được | Contract/integration tests |
| Serving test traffic | Đã nhận traffic kiểm thử | Synthetic, test journey |
| Serving canary | Đã nhận một phần traffic thật có kiểm soát | SLI theo version/cohort |
| Primary | Đang chịu trách nhiệm chính | Routing/source-of-truth rõ |
| Stable | Đã qua cửa sổ xác minh | SLO, dữ liệu, incident review |
| Legacy read-only | Thành phần cũ không còn nhận ghi mới | Quyền ghi bị khóa và audit |
| Decommissioned | Hạ tầng cũ đã ngừng an toàn | Dependency inventory, backup, audit |

**Deployed không đồng nghĩa production-ready; serving traffic không đồng nghĩa source of truth đã chuyển; source of truth chuyển không đồng nghĩa dữ liệu cũ có thể xóa.**

Mỗi dự án nên định nghĩa trước điều kiện vào và ra cho từng trạng thái. Nếu nhóm chỉ dùng một nhãn “done”, các quyết định quan trọng như ngừng dual-write, khóa API cũ hay xóa database dễ bị quyết định theo cảm giác.

## 2. Tách bốn quyết định thường bị gộp

### 2.1. Cutover

Cutover thay đổi nơi nhận traffic hoặc nơi thực hiện nghiệp vụ chính. Nó có thể xảy ra theo:
- Một lần cho toàn bộ traffic.
- Theo phần trăm traffic hoặc canary cohort.
- Theo tenant, region, loại giao dịch hoặc phiên bản client.
- Theo một capability riêng trong Strangler migration.
- Theo từng bảng dữ liệu hoặc nhóm record, nếu source of truth được kiểm soát.

Cutover cần có **điều kiện bắt đầu, điều kiện tiếp tục, ngưỡng dừng, owner và phương án phục hồi**.

### 2.2. Rollback

Rollback đưa ứng dụng, routing, config hoặc một thành phần về trạng thái trước. Nhưng nó không tự đảo ngược:
- Giao dịch đã ghi vào database mới.
- Event đã phát lên broker.
- Email/SMS đã gửi.
- Payment đã capture.
- Dữ liệu đã biến đổi theo schema mới.
- Client đã nhận payload mới và lưu lại.

Vì vậy rollback phải trả lời: **đã có side effect nào xảy ra và hệ thống cũ có hiểu được chúng không?**

### 2.3. Roll-forward

Nếu dữ liệu hoặc hợp đồng đã tiến tới trạng thái mới, quay lui có thể gây mất mát. Roll-forward là phương án tiếp tục sửa trên hệ thống mới, có thể bằng hotfix, feature flag, adapter hoặc khôi phục một capability trong phiên bản mới.

Cần có điều kiện chọn roll-forward thay vì rollback trước khi incident xảy ra. Không nên tranh luận lần đầu trong lúc production đang hỏng.

### 2.4. Decommission

Ngừng legacy là một thay đổi có rủi ro riêng. Một server không còn nhận traffic vẫn có thể đang được dùng cho:
- Batch job chạy hàng tháng.
- Đối soát cuối kỳ.
- Client cũ không còn được nhìn thấy trong dashboard.
- Báo cáo pháp lý hoặc audit.
- Replay event lịch sử.
- Backup restore.
- DNS hoặc certificate cũ.
- Một integration của đối tác.

**Không có traffic trong vài giờ không phải bằng chứng không còn consumer.**

## 3. Thiết lập tiêu chí thành công trước khi bắt đầu migration

Một kế hoạch chuyển đổi cần ghi ít nhất:

1. **Business outcome:** capability nào phải tiếp tục hoạt động và trạng thái nào được coi là thành công.
2. **Scope:** service, endpoint, event, tenant, region, dữ liệu và client nằm trong phạm vi.
3. **Source of truth:** hệ thống nào có quyền quyết định trạng thái cuối cùng của mỗi loại dữ liệu.
4. **Compatibility window:** các phiên bản producer/consumer hoặc schema nào phải cùng tồn tại.
5. **SLI/SLO:** success rate, latency, freshness, correctness và availability.
6. **Data integrity:** invariant, reconciliation và cách phát hiện mất/trùng/sai record.
7. **Security:** identity, permission, encryption, audit, retention và compliance.
8. **Recovery:** rollback/roll-forward, RTO/RPO, backup và người có quyền quyết định.
9. **Ownership:** incident commander, service owner, data owner, platform/security contact.
10. **Decommission conditions:** bằng chứng consumer cũ đã hết, dữ liệu được lưu đúng và dependency được thu hồi.
11. **Cost boundary:** chi phí dual-run, thời gian giữ hệ thống cũ và thời điểm chấm dứt.
12. **Approval authority:** ai phê duyệt chuyển bước theo mức rủi ro.

Mục tiêu phải đo được. Ví dụ “hệ thống mới hoạt động tốt” quá mơ hồ. Một tiêu chí tốt hơn là: “Tỷ lệ giao dịch hoàn tất của cohort canary đạt SLO đã phê duyệt, không tăng tỷ lệ duplicate payment, p95 latency nằm trong ngân sách và reconciliation không có sai lệch chưa giải thích trong cửa sổ xác minh”.

Không dùng một con số chung cho mọi dự án; mục tiêu phải theo critical journey và rủi ro dữ liệu cụ thể.

## 4. Xác định phạm vi chuyển đổi và ranh giới trách nhiệm

Trước khi chọn ngày cutover, lập inventory:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| API/route | Client nào gọi? Có cache/CDN/gateway không? |
| Event/topic/queue | Ai publish/consume? Retention và replay ra sao? |
| Database/table | Ai đọc/ghi? Có trigger, view, procedure, CDC không? |
| Batch/scheduler | Job nào chạy theo giờ/ngày/tháng? |
| File/object storage | Có file import/export hoặc reference cũ không? |
| Identity/secret | Service account, certificate, key nào còn dùng? |
| Network/DNS | Route, firewall, NAT, private endpoint nào còn cần? |
| Monitoring | Alert/dashboard nào gắn với legacy? |
| Backup/DR | Restore procedure có phụ thuộc hệ thống cũ không? |
| External partner | Có consumer ngoài tổ chức hoặc client lâu cập nhật không? |

Một hệ thống legacy thường có dependency không nằm trong source code chính: cron job, ETL, report, script vận hành, tài khoản thủ công và đối tác. Dùng nhiều nguồn inventory: code search, access log, database audit, message metadata, scheduler catalog, cloud resource tags và phỏng vấn owner.

Mỗi dependency cần **owner và bằng chứng**, không chỉ một dòng tên trong sơ đồ.

## 5. Phân loại thay đổi theo khả năng đảo ngược

Không phải mọi cutover đều có cùng khả năng rollback. Phân loại trước:

| Loại thay đổi | Ví dụ | Khả năng quay lui |
|---|---|---|
| Stateless/config | Route hoặc feature flag | Thường cao nếu config cũ còn hợp lệ |
| Application version | Deploy image mới | Cao nếu schema/side effect tương thích |
| Additive schema | Thêm cột optional | Thường có thể giữ schema và rollback code |
| Data transformation | Chuyển đơn vị hoặc normalize record | Cần backup, mapping và reverse/forward plan |
| Source-of-truth switch | Chuyển nơi quyết định order state | Rủi ro cao, cần fencing và reconciliation |
| External side effect | Payment capture, email, shipment | Không thể đảo ngược hoàn toàn |
| Destructive cleanup | Drop table, xóa bucket/key | Có thể không phục hồi nếu thiếu backup |
| Contract removal | Bỏ API/event version cũ | Chỉ an toàn khi mọi consumer đã chuyển |

Một nguyên tắc hữu ích: **thay đổi có thể đảo ngược nên được thực hiện sớm; thay đổi phá hủy hoặc không thể đảo ngược nên thực hiện sau khi đã có bằng chứng đủ mạnh và phương án phục hồi riêng.**

Ví dụ: thêm cột mới thường có thể làm trước; xóa cột cũ nên để cuối. Deploy code hỗ trợ cả hai schema trước; chỉ bỏ khả năng đọc cũ khi không còn dữ liệu/consumer cần nó.

## 6. Thiết kế migration theo các giai đoạn

Một lộ trình tổng quát:

~~~mermaid
flowchart LR
    A["Inventory và baseline"] --> B["Expand compatibility"]
    B --> C["Migrate data và consumers"]
    C --> D["Shadow / canary"]
    D --> E["Cutover có kiểm soát"]
    E --> F["Observe và reconcile"]
    F --> G{"Đạt tiêu chí ổn định?"}
    G -->|Chưa| H["Rollback hoặc roll-forward"]
    H --> F
    G -->|Đạt| I["Legacy read-only"]
    I --> J["Decommission"]
~~~

Không nhất thiết dự án nào cũng cần tất cả bước. Nhưng một migration dữ liệu hoặc thay source of truth thường cần nhiều hơn một lần deploy.

### Giai đoạn 1 — Baseline

- Ghi traffic, lỗi, latency, throughput và business outcomes hiện tại.
- Lưu số lượng record, invariant và data freshness.
- Inventory client, consumer, job, integration và quyền.
- Đo cost, capacity, backup và recovery time.
- Chốt tiêu chí thành công và ngưỡng rollback.

### Giai đoạn 2 — Expand

- Thêm endpoint/field/schema mới theo cách tương thích.
- Nâng reader để hiểu dữ liệu cũ và mới.
- Cấp quyền và telemetry cho hệ thống mới.
- Chuẩn bị route/feature flag nhưng chưa chuyển toàn bộ traffic.
- Test rollback khi chưa có dữ liệu mới và khi đã có dữ liệu mới.

### Giai đoạn 3 — Migrate

- Backfill dữ liệu theo batch.
- Chuyển consumer/client theo cohort.
- Shadow-read hoặc so sánh kết quả.
- Theo dõi lag, duplicate, missing và conflict.
- Chỉ cho phép một nguồn ghi có thẩm quyền theo từng aggregate/record.

### Giai đoạn 4 — Cutover

- Chuyển một phần traffic trước.
- Xác minh SLI và data correctness.
- Tăng traffic theo các bước đã định.
- Giữ nút dừng và owner trực.
- Ghi chính xác timestamp, version, config và cohort.

### Giai đoạn 5 — Stabilize

- Duy trì cửa sổ xác minh đủ dài cho chu kỳ nghiệp vụ.
- Chạy reconciliation độc lập.
- Kiểm tra batch, report, refund, retry và replay.
- Đánh giá error budget, incident và support tickets.
- Xác nhận source of truth mới.

### Giai đoạn 6 — Retire

- Chặn ghi mới vào legacy.
- Quan sát read-only và consumer còn tồn tại.
- Archive dữ liệu theo retention.
- Thu hồi secret, IAM, route và hạ tầng.
- Xác minh backup/restore không còn phụ thuộc hệ thống đang xóa.
- Đóng migration bằng chứng và owner.

## 7. Expand–migrate–contract để giữ phiên bản cũ và mới cùng tồn tại

Khi thay API hoặc schema, không nên deploy producer mới rồi giả định mọi consumer lập tức nâng cấp.

~~~text
EXPAND
  Thêm khả năng mới, giữ contract cũ
       |
       v
MIGRATE
  Nâng consumer, chuyển traffic/data, kiểm tra
       |
       v
VERIFY
  Chứng minh không còn sử dụng đường cũ
       |
       v
CONTRACT
  Bỏ endpoint/field/schema cũ
~~~

Ví dụ thay trường shipping_note bằng delivery_instruction:
1. Thêm cột mới và giữ cột cũ.
2. Code mới có thể đọc cả hai, với quy tắc ưu tiên rõ.
3. Chuyển ghi theo chiến lược được chọn và kiểm tra nhất quán.
4. Backfill dữ liệu cũ.
5. Chuyển từng consumer sang cột mới.
6. Quan sát usage của cột cũ qua query/audit.
7. Chỉ xóa cột cũ khi đã qua thời hạn rollback và retention.

Nếu hai trường có semantics khác nhau, không nên giả vờ chúng tương đương chỉ vì cùng kiểu string. Hợp đồng phải mô tả ý nghĩa nghiệp vụ và quy tắc chuyển đổi.

## 8. Xác định source of truth trong thời kỳ chuyển tiếp

Một trong những rủi ro lớn nhất là **hai hệ thống cùng nghĩ mình là nơi có quyền ghi cuối cùng**.

Cần ghi rõ cho từng loại dữ liệu:
- Hệ thống nào được tạo record mới?
- Hệ thống nào được sửa trạng thái?
- Ai cấp ID và version?
- Event nào là bằng chứng commit?
- Hệ thống còn lại là replica, projection hay adapter?
- Xử lý conflict theo version, timestamp hay quy tắc nghiệp vụ nào?
- Khi dữ liệu khác nhau, nguồn nào được tin cậy và ai quyết định?

Ví dụ:
- Trước cutover: Legacy Orders là writer chính.
- Trong backfill: New Orders nhận bản sao và xây read model.
- Trong shadow: New Orders tính kết quả nhưng không phát side effect.
- Sau cutover: New Orders là writer chính cho cohort đã chuyển; legacy chỉ đọc.
- Rollback: không được tự động cho legacy ghi lại nếu nó chưa nhận đầy đủ các thay đổi mới.

**Source of truth phải được xác định theo aggregate hoặc miền dữ liệu**, không chỉ nói chung “database mới là chính”.

### 8.1. Fencing để ngăn hai writer cùng hoạt động

Có thể dùng:
- Một writer lease có fencing token tăng dần.
- Quyền DB chỉ cho một writer trong giai đoạn.
- Routing/feature flag có version và audit.
- Optimistic locking hoặc version column.
- Idempotency key và deduplication.
- Transactional outbox để bảo đảm event gắn với commit.
- Control plane ghi nhận epoch/owner hiện hành.

Một boolean config có thể chưa đủ nếu hai instance cũ và mới cùng chạy, cache flag khác nhau hoặc một worker cũ chưa dừng. Cần cơ chế để writer cũ bị từ chối khi quyền sở hữu đã chuyển.

## 9. Shadow traffic: so sánh trước khi giao quyền phục vụ

Shadowing gửi bản sao request hoặc input sang hệ thống mới để so kết quả mà **không để hệ thống shadow gây side effect**.

~~~mermaid
flowchart LR
    C["Client request"] --> L["Legacy primary"]
    C -. "shadow copy" .-> N["New system"]
    L --> R["Response to client"]
    L --> O["Observed result"]
    N --> X["Comparison pipeline"]
    O --> X
~~~

Dùng shadow để:
- So response theo field nghiệp vụ.
- So kết quả tính giá, eligibility, routing.
- Kiểm tra latency và resource usage.
- Phát hiện dữ liệu không đủ hoặc semantics khác.
- Đánh giá behavior trên traffic thật đã được phép xử lý.

Không được gửi shadow request làm:
- Capture payment hai lần.
- Tạo hai order thật.
- Gửi hai email/SMS.
- Tạo shipment trùng.
- Ghi audit event như giao dịch thật.
- Làm thay đổi inventory.

Cần một chế độ dry-run hoặc mock external side effects, identity riêng và bộ lọc dữ liệu nhạy cảm. Shadow không phải phép thử vô hại nếu service mới có quyền ghi.

## 10. Canary và progressive delivery

Canary chuyển một phần traffic sang hệ thống mới, sau đó tăng dần khi các chỉ số đạt ngưỡng.

Ví dụ lộ trình:
- 0%: chỉ shadow và test.
- 1%: cohort nội bộ/tenant thử nghiệm.
- 5%: traffic nhỏ có đại diện.
- 25%: tăng phạm vi.
- 50%: kiểm chứng tải và phân phối.
- 100%: cutover chính nếu mọi điều kiện đạt.

Các tỷ lệ chỉ minh họa. Với giao dịch tài chính hoặc dữ liệu có side effect, cohort và tỷ lệ phải theo threat/risk analysis. Không tăng theo thời gian cố định nếu metric chưa đạt.

Mỗi bước cần:
- Minimum sample size.
- SLO/SLI theo version và cohort.
- So sánh với control/baseline.
- Thời gian quan sát đủ cho luồng nghiệp vụ.
- Ngưỡng stop và owner có quyền dừng.
- Kiểm tra side effects, duplicate và data correctness.
- Capacity để phục vụ cả hai hệ thống khi dual-run.

Canary có thể không phát hiện lỗi hiếm, lỗi cuối tháng hoặc lỗi chỉ xảy ra ở tenant đặc biệt. Kết hợp synthetic, reconciliation và các test theo dữ liệu đại diện.

## 11. Chọn chỉ số để quyết định cutover

Một bộ tiêu chí nên bao phủ nhiều khía cạnh:

| Nhóm | Ví dụ chỉ số | Điều kiện ra quyết định |
|---|---|---|
| Availability | Good request ratio, uptime theo SLI | Đạt SLO đã duyệt |
| Latency | p95/p99, timeout, queue age | Không vượt ngân sách |
| Correctness | Mismatch, missing, duplicate, invalid state | Không còn sai lệch chưa giải thích vượt ngưỡng |
| Freshness | Replication lag, event age, data delay | Nằm trong deadline nghiệp vụ |
| Capacity | CPU/RAM, DB pool, queue throughput | Đủ headroom cho peak/failure |
| Security | Auth failures, permission audit, policy | Không có vi phạm chưa xử lý |
| Business | Checkout/payment completion, reconciliation | Kết quả nghiệp vụ đúng |
| Operations | Alert, runbook, rollback readiness | Owner và đường ứng phó sẵn sàng |
| Support | Ticket/complaint, manual workaround | Không có xu hướng xấu bất thường |
| Cost | Dual-run, resource utilization | Nằm trong ngân sách đã chấp thuận |

Không có một ngưỡng số cố định cho mọi hệ thống. Ví dụ mismatch 0 có thể là yêu cầu bắt buộc với số dư tài chính; với search index eventual consistency, một độ trễ ngắn có thể nằm trong hợp đồng. Mỗi metric cần có **định nghĩa, nguồn dữ liệu, cửa sổ, mẫu tối thiểu và người chịu trách nhiệm**.

## 12. Định nghĩa data correctness trước khi so sánh

Một response giống nhau không chứng minh hai hệ thống có dữ liệu giống nhau. Cần xác định invariant:

- Mỗi order có một ID ổn định.
- Tổng tiền = tổng line item + thuế/phí - giảm giá theo quy tắc.
- Payment capture không vượt authorized amount.
- Một message nghiệp vụ không làm phát sinh side effect trùng.
- Mọi trạng thái chuyển theo state machine hợp lệ.
- Quan hệ foreign key hoặc aggregate consistency được giữ.
- Record đã commit không bị mất khi restart/replay.
- Dữ liệu nhạy cảm có đúng quyền truy cập và retention.

Các phép kiểm:
- Count theo trạng thái, ngày, tenant và region.
- Aggregate totals có kiểm soát đơn vị/rounding.
- Hash/checksum theo partition hoặc record key.
- Anti-join tìm missing records.
- Duplicate key và idempotency conflict.
- Version/sequence gaps.
- Reconciliation từ nguồn có thẩm quyền độc lập.

Đối với dữ liệu tiền tệ, không chỉ so floating-point tổng; cần quy tắc decimal, currency, rounding và thời điểm capture. Một sai lệch nhỏ có thể là bug nghiêm trọng.

## 13. Data migration: kiểm tra trước, trong và sau cutover

Một kế hoạch data migration cần:

1. **Schema mapping:** trường nguồn/đích, kiểu, nullability, default và semantics.
2. **Inventory:** số record, dung lượng, partition, retention và lịch sử.
3. **Transform:** quy tắc normalize, timezone, currency, encoding và ID.
4. **Backfill:** batch size, rate limit, checkpoint và resume.
5. **Incremental sync:** CDC, outbox, event hoặc dual-write được kiểm soát.
6. **Validation:** counts, checksums, invariants và sampled deep checks.
7. **Cutover:** writer ownership, freeze window nếu cần và lag threshold.
8. **Reconciliation:** so dữ liệu phát sinh trong khoảng chuyển tiếp.
9. **Recovery:** backup, replay, mapping ngược hoặc roll-forward.
10. **Retention:** giữ nguồn cũ trong thời gian cần audit/rollback.

Không thực hiện một câu lệnh UPDATE toàn bảng mà không thử trên snapshot đại diện, đo lock/replication lag và xác định cách resume. Backfill phải có checkpoint để job bị dừng không làm trùng side effects.

### 13.1. Backfill và incremental changes

Nếu snapshot được chụp lúc T0, trong khi người dùng vẫn thay đổi dữ liệu, chỉ copy snapshot là chưa đủ. Có thể:
- Chạy snapshot rồi apply change log/CDC từ T0.
- Dùng outbox event có offset/sequence đáng tin.
- Tạm ngừng ghi trong cửa sổ ngắn đã duyệt.
- Chuyển từng partition/tenant với writer fencing.

Cần biết **điểm bắt đầu và điểm kết thúc của change stream**. Nếu không, có thể bỏ sót thay đổi xảy ra giữa snapshot và lúc bật hệ thống mới.

## 14. Dual-write: chỉ dùng khi có chiến lược nhất quán

Dual-write là ghi cùng một thay đổi vào hai hệ thống. Nó có thể giúp migration nhưng tạo các failure mode:
- Ghi nguồn A thành công, B thất bại.
- B thành công, A timeout nhưng thực ra đã commit.
- Retry làm record trùng.
- Hai hệ thống nhận sự kiện không theo thứ tự.
- Một hệ thống áp dụng transform khác.
- Rollback code nhưng dữ liệu mới đã được ghi.
- Một bên trở thành stale mà không có alert.

Nếu cần dual-write, phải có:
- Một nguồn quyết định và quy tắc reconcile.
- Idempotency key/version.
- Outbox hoặc transaction phù hợp.
- Retry có giới hạn và DLQ.
- Theo dõi divergence/lag.
- Quy trình replay và sửa lệch.
- Điều kiện kết thúc dual-write.
- Cơ chế tránh hai writer cùng giành quyền.

**Dual-write không phải transaction phân tán tự động.** Nếu hai database độc lập, một transaction local không thể bảo đảm commit nguyên tử trên cả hai. Có thể chọn một writer và đồng bộ replica bất đồng bộ, hoặc dùng saga/workflow phù hợp với nghiệp vụ.

## 15. Cutover database: tiêu chí cụ thể

Một checklist trước khi chuyển writer:

- Backfill đã hoàn tất và validation đạt.
- CDC/outbox lag dưới ngưỡng đã duyệt.
- Consumer mới xử lý được lịch sử cần thiết.
- Schema cũ và mới còn tương thích trong cửa sổ rollback.
- Connection pool, capacity và index đã sẵn sàng.
- Backup/restore đã thử với dữ liệu tương ứng.
- Read/write permissions đúng.
- Fencing ngăn writer cũ.
- Idempotency và retry không gây duplicate.
- Reconciliation job có owner.
- Runbook và incident contact có sẵn.
- Cutover owner và thời điểm quyết định được ghi nhận.

Sau cutover:
- Theo dõi write success, transaction latency, lock, replication lag.
- So counts, totals và state transitions.
- Kiểm tra các job định kỳ.
- Không xóa database cũ chỉ vì app mới đã ghi thành công vài giờ.

## 16. Chuyển message broker hoặc event schema

Khi thay broker hoặc schema registry, phải xét:
- Producer nào đang publish?
- Consumer group nào đang đọc?
- Offset/checkpoint có thể chuyển không?
- Retention của topic cũ còn bao lâu?
- Có message chưa xử lý hoặc DLQ không?
- Ordering/key partition có được giữ?
- Consumer có idempotent không?
- Replay từ nguồn cũ có cần không?
- Schema version lịch sử còn được giải mã không?
- ACL, TLS, certificate và network route mới đã đủ?

Một broker mới có thể nhận traffic mới nhưng **message cũ vẫn nằm ở broker cũ**. Trước decommission, cần drain hoặc migrate message, xử lý DLQ, xác nhận consumer lag = 0 theo định nghĩa, và lưu bằng chứng retention.

Không chỉ nhìn consumer process khỏe. Cần kiểm tra event business cuối cùng đã được xử lý, không còn offset gap hoặc message bị poison.

## 17. API cutover và client cũ

Một API có thể được gọi bởi:
- Web/mobile clients.
- Partner integrations.
- Batch job.
- Internal service.
- Script vận hành.
- CDN/cache.
- Một client cũ rất ít hoạt động nhưng vẫn tồn tại.

Khi chuyển endpoint:
1. Inventory access logs theo client/version/credential.
2. Công bố API contract và deprecation policy.
3. Deploy consumer hỗ trợ cả endpoint cũ/mới khi cần.
4. Dùng gateway routing hoặc adapter có thể quan sát.
5. Canary theo tenant/client cohort.
6. Theo dõi usage endpoint cũ và lỗi auth/timeout.
7. Gửi thông báo theo kênh hỗ trợ đã thỏa thuận.
8. Chặn dần client cũ sau deadline và điều kiện đã công bố.
9. Giữ phương án hỗ trợ hoặc trả lỗi nâng cấp rõ ràng.

Một ngày không có request chưa chắc đủ; client có thể chạy theo tháng, quý hoặc chỉ hoạt động khi một khách hàng cụ thể thực hiện quy trình đặc biệt.

## 18. Định nghĩa rollback trigger trước cutover

Rollback trigger cần là điều kiện có thể quan sát và gắn với tác động, ví dụ:
- Success rate của critical journey thấp hơn ngưỡng trong cửa sổ xác nhận.
- p99 latency vượt budget liên tục và ảnh hưởng timeout.
- Data mismatch hoặc duplicate vượt zero-tolerance policy.
- Replication lag vượt RPO.
- Authorization/security policy không đáp ứng.
- Queue age/backlog vượt deadline.
- Một failure mode không thể khôi phục trong RTO.
- Error budget burn đạt ngưỡng page đã định.
- Capacity không đủ để tiếp tục rollout an toàn.

Không dùng tiêu chí mơ hồ như “nếu thấy không ổn”. Cũng không đặt trigger chỉ dựa CPU cao nếu user journey vẫn đạt và không có risk đã định.

Mỗi trigger cần:
- Metric/query nguồn.
- Cửa sổ quan sát.
- Sample size.
- Owner ra quyết định.
- Hành động dừng rollout.
- Điều kiện rollback hoặc roll-forward.
- Bằng chứng được ghi vào timeline.

## 19. Rollback không luôn là lựa chọn an toàn

Trước khi rollback, kiểm tra:

| Câu hỏi | Nếu câu trả lời là không |
|---|---|
| Bản cũ đọc được dữ liệu mới? | Không rollback writer/reader một cách mù |
| Message mới có thể xử lý bởi consumer cũ? | Giữ adapter/reader mới hoặc replay có chuyển đổi |
| External side effects có thể hoàn tác? | Reconcile/compensate, không lặp thao tác |
| DB schema vẫn tương thích? | Có thể cần roll-forward hoặc migration phục hồi |
| Feature flag có đảo ngược được state? | Tắt flag không đủ nếu data đã đổi |
| Secret/config cũ còn hiệu lực và an toàn? | Cấp lại hoặc dùng phương án khác |
| Route/DNS rollback có propagation delay? | Tính thời gian và cache TTL |
| Backup restore có đạt RTO/RPO? | Không coi restore là nút bấm tức thì |

Một rollback thành công về process nhưng làm hỏng dữ liệu hoặc giao dịch mới không phải phục hồi thành công.

### 19.1. Quyết định rollback hay roll-forward

~~~mermaid
flowchart TD
    A["Phát hiện regression sau cutover"] --> B{"Có user/data impact?"}
    B -->|Không| C["Dừng rollout, điều tra"]
    B -->|Có| D{"Bản cũ tương thích dữ liệu và side effects hiện tại?"}
    D -->|Có| E["Rollback có kiểm soát"]
    D -->|Không| F{"Có mitigation an toàn trên bản mới?"}
    F -->|Có| G["Roll-forward / disable capability"]
    F -->|Không| H["Incident command: cô lập và phục hồi theo DR"]
    E --> I["Reconcile và xác nhận SLO"]
    G --> I
    H --> I
~~~

Đây là mô hình ra quyết định tổng quát; trong thực tế cần tính severity, RTO, quyền phê duyệt và nghĩa vụ pháp lý.

## 20. Roll-forward: chuẩn bị trước phương án sửa trên đích mới

Nếu rollback không an toàn, cần:
- Feature flag để tắt phần logic mới nhưng giữ schema reader.
- Adapter chuyển payload về semantics cũ.
- Hotfix có đường build/deploy nhanh đã được kiểm chứng.
- Traffic shift sang vùng/instance khỏe.
- Rate limit/backpressure bảo vệ data tier.
- Compensation workflow cho side effects.
- Reconciliation để tìm record sai.
- Runbook và incident commander có quyền quyết định.

Roll-forward không có nghĩa “cứ deploy tiếp và hy vọng”. Nó cần giới hạn blast radius, kiểm soát dữ liệu và xác nhận SLO như một phương án recovery thực sự.

## 21. RTO, RPO và cửa sổ rollback

**RTO (Recovery Time Objective)** là thời gian mục tiêu để khôi phục một dịch vụ/quy trình sau sự cố. **RPO (Recovery Point Objective)** là mức mất dữ liệu tối đa có thể chấp nhận, thường biểu diễn bằng thời gian dữ liệu.

Ví dụ:
- RTO = 60 phút.
- RPO = 5 phút.
- Một migration mất 30 phút để chuyển route.
- Backup cuối cách thời điểm sự cố 20 phút.

Dù route có thể rollback trong 2 phút, nếu dữ liệu sau backup bị mất 20 phút thì phương án đó không đạt RPO. **Khôi phục availability và khôi phục dữ liệu là hai điều kiện khác nhau.**

Cửa sổ rollback phải xét:
- Thời điểm schema cũ không còn đọc dữ liệu mới.
- Thời điểm message mới bắt đầu phát.
- Thời điểm external side effect không thể hoàn tác.
- Retention của event/backup.
- Thời gian đồng bộ dữ liệu về legacy.
- Khả năng dựng lại từ source of truth.

Sau khi cửa sổ rollback kết thúc, runbook phải chuyển rõ sang **roll-forward/DR**. Không để đội trực nghĩ có thể quay lại bất kỳ lúc nào.

## 22. Cutover theo phần trăm, tenant hoặc region

Một cách an toàn hơn all-at-once:
- Theo tenant nội bộ trước.
- Theo region ít rủi ro hoặc có dữ liệu đại diện.
- Theo cohort được xác định bằng hash ổn định.
- Theo loại request không có side effect lớn trước.
- Theo read path trước write path.
- Theo từng capability trong Strangler pattern.

Khi phân cohort, giữ routing ổn định để một khách hàng không luân phiên giữa hai nguồn dữ liệu không tương thích. Nếu order của cùng tenant bị chia sang hai hệ thống, cần bảo đảm ID và source of truth không xung đột.

Mỗi cohort phải có:
- Tiêu chí chọn.
- Tỷ lệ traffic.
- SLO và data metrics.
- Điều kiện mở rộng.
- Điều kiện dừng.
- Owner.
- Thời điểm hết thời hạn.
- Quy tắc chuyển cohort trở lại nếu rollback.

## 23. Cửa sổ xác minh phải bao phủ chu kỳ nghiệp vụ

Một service online 24 giờ không chứng minh các luồng chạy mỗi tháng đã ổn. Ví dụ:
- Settlement chạy cuối ngày.
- Invoice generation chạy đầu tháng.
- Payroll chạy theo chu kỳ.
- Reconciliation chạy sau khi đối tác gửi file.
- Backup restore diễn tập theo quý.
- Client mobile cũ chỉ mở app vài tuần một lần.

Cửa sổ ổn định cần đủ dài để quan sát **các chu kỳ quan trọng trong phạm vi migration**, hoặc có test/diễn tập đại diện cho những chu kỳ ít xảy ra.

Có thể dùng:
- Minimum elapsed time.
- Minimum business transaction count.
- Ít nhất một lần chạy batch đại diện.
- Đối soát tất cả cohort/partition.
- Không còn consumer cũ theo telemetry trong support window.
- Không có lỗi chưa giải thích ở critical journey.

Không dùng một con số “7 ngày” cho mọi migration. Một API realtime có thể có đủ mẫu trong vài giờ; một hệ thống settlement chỉ có đủ bằng chứng sau chu kỳ cuối tháng.

## 24. Cửa sổ hỗ trợ phiên bản cũ và deprecation

Trước khi bỏ API, event hoặc schema cũ:
- Công bố version bị deprecate và ngày dự kiến ngừng.
- Xác định owner của consumer.
- Đo usage theo version, credential, tenant và route.
- Gửi cảnh báo/notice qua kênh phù hợp.
- Có tài liệu migration và ví dụ.
- Hỗ trợ các client ngoài tổ chức theo hợp đồng.
- Xác định điều kiện gia hạn ngoại lệ.
- Xử lý dữ liệu lịch sử và replay.
- Đặt ngày kết thúc support sau khi các điều kiện đạt.

**Không xóa API chỉ vì số request thấp** nếu còn một đối tác hoặc quy trình quan trọng dùng theo mùa. Usage telemetry phải được đọc trong bối cảnh chu kỳ business và thỏa thuận hỗ trợ.

## 25. Decommission checklist: chứng minh không còn dependency

Trước khi ngừng legacy, xác minh:

**Traffic và client**
- Không còn route/traffic production hợp lệ.
- Client cũ đã nâng hoặc được thông báo.
- CDN, DNS, webhook và partner endpoint đã chuyển.
- Batch/script/scheduler không gọi legacy.

**Data**
- Source of truth mới đã được xác nhận.
- Backfill, CDC và reconciliation hoàn tất.
- DLQ, replay, historical event và audit được xử lý.
- Backup/retention đáp ứng chính sách.
- Restore không phụ thuộc server đang xóa.
- Data owner phê duyệt xóa hoặc archive.

**Security và identity**
- Không còn credential/service account được sử dụng.
- Certificate, key, secret được rotate/revoke đúng lúc.
- Firewall, security group, IAM và network route được thu hồi.
- Audit evidence được lưu.
- Không bỏ sót account dùng cho job định kỳ.

**Operations**
- Alert, dashboard, runbook và on-call ownership đã chuyển.
- Monitoring không còn báo nhầm thành phần cũ.
- Resource inventory và cost tags được cập nhật.
- Incident recovery không còn phụ thuộc legacy.
- Platform/DB/security owner đã xác nhận phần việc.

**Governance**
- Retention/legal hold được xem xét.
- Hợp đồng hỗ trợ và nghĩa vụ thông báo đã hoàn tất.
- Quyết định decommission có owner, ngày và bằng chứng.
- Kế hoạch xử lý nếu phát hiện dependency sau khi tắt đã được xác định.

## 26. Decommission theo từng lớp, không xóa một lần

Một thứ tự thường an toàn:

1. Chuyển traffic và khóa tính năng mới trên legacy.
2. Đưa legacy vào read-only hoặc maintenance mode.
3. Theo dõi access log và audit trong cửa sổ đủ đại diện.
4. Chuyển batch/report/replay và consumer còn lại.
5. Export/archive dữ liệu theo retention và quyền truy cập.
6. Thu hồi writer credentials.
7. Thu hồi các route, scheduler và integration.
8. Dừng process/instance.
9. Giữ snapshot/backup theo chính sách.
10. Xóa tài nguyên hết retention và không còn legal hold.
11. Thu hồi DNS, certificate, secret và pipeline.
12. Cập nhật catalog, CMDB, runbook và cost allocation.

Có thể giữ một snapshot hoặc archive lâu dài mà không cần giữ cả compute stack luôn bật. Tuy nhiên, archive phải có người sở hữu, cơ chế đọc/restore, encryption và chi phí lưu trữ được dự toán.

## 27. Read-only không đồng nghĩa đã ngừng

Đặt legacy read-only là một bước kiểm soát hữu ích:
- Từ chối ghi mới ở application và database permission.
- Ghi audit nếu có request ghi bị từ chối.
- Giữ read access cho report hoặc đối chiếu trong thời hạn được phép.
- Giám sát các client còn truy cập.
- Kiểm tra các job bị lỗi vì vẫn cố ghi.
- Đảm bảo không có trigger/procedure âm thầm ghi dữ liệu.

Không chỉ ẩn nút UI hoặc tắt endpoint ở gateway trong khi service account vẫn có quyền DB write. Quyền phải được kiểm soát ở lớp thực thi phù hợp.

Nếu có consumer đọc legacy trong thời gian archive, phải xác định SLO, owner và thời hạn hỗ trợ; không giữ một thành phần không người quản lý vô thời hạn.

## 28. Xử lý dữ liệu lịch sử và legal retention

Ngừng ứng dụng không có nghĩa được xóa mọi dữ liệu. Có thể cần giữ:
- Giao dịch tài chính và audit.
- Hồ sơ hợp đồng.
- Lịch sử consent.
- Dữ liệu phục vụ dispute.
- Event phục vụ replay hoặc điều tra.
- Backup trong retention đã cam kết.

Cần phân biệt:
- **Hot operational data:** hệ thống mới dùng thường xuyên.
- **Archive:** dữ liệu ít truy cập nhưng phải giữ.
- **Backup:** bản phục hồi trong thời hạn.
- **Legal hold:** dữ liệu bị khóa xóa theo nghĩa vụ.
- **Data deletion:** xóa theo chính sách quyền riêng tư/retention.

Archive phải có:
- Data owner.
- Schema và format có thể đọc trong tương lai.
- Encryption/key lifecycle.
- Access audit.
- Retention và deletion date.
- Quy trình restore được thử.
- Khả năng chứng minh tính toàn vẹn.

Đừng giữ nguyên một máy chủ production chỉ vì sợ mất dữ liệu lịch sử nếu có phương án archive an toàn; cũng đừng xóa archive khi nghĩa vụ lưu trữ còn tồn tại.

## 29. DNS, cache và routing có thể làm cutover kéo dài hơn dự kiến

Khi đổi DNS hoặc endpoint:
- Resolver có TTL khác nhau.
- CDN/proxy có thể cache route hoặc response.
- Connection pool giữ kết nối cũ.
- Client mobile có endpoint hard-code trong phiên bản cũ.
- Một số consumer giữ DNS cache lâu hơn TTL.
- Webhook/partner cần thời gian cập nhật.

Vì vậy, cutover phải đo **traffic thực sự tới hệ thống cũ và mới**, không chỉ kiểm tra DNS record đã thay.

Các biện pháp:
- Dùng gateway routing khi có thể kiểm soát tập trung.
- Giảm TTL trước cửa sổ chuyển đổi nếu chính sách cho phép.
- Theo dõi connection draining và active requests.
- Giữ endpoint cũ như adapter/redirect trong thời hạn hỗ trợ.
- Không đóng firewall ngay khi DNS đã đổi.
- Có cách xác định client version và nguồn traffic.

Đừng giữ hai hệ thống mở ghi chỉ vì DNS cache có thể chậm. Routing transition và source-of-truth ownership phải được thiết kế cùng nhau.

## 30. Feature flag và kill switch trong cutover

Feature flag có thể tách việc deploy code khỏi bật behavior. Nó giúp:
- Bật capability theo cohort.
- Dừng phần tính năng lỗi mà giữ service còn chạy.
- Chuyển traffic theo nhóm.
- Chạy shadow/read comparison.
- Mở rộng dần sau khi SLO đạt.

Nhưng cần:
- Owner, purpose và expiry date.
- Giá trị mặc định an toàn nếu flag service không truy cập được.
- Quy tắc đồng bộ và audit thay đổi.
- Metric theo trạng thái flag/cohort.
- Kiểm tra side effects đã phát sinh.
- Xác minh flag tắt có thật sự ngăn hành vi mới.

Một flag không xóa event đã phát, không đảo payment capture và không đưa dữ liệu mới về schema cũ. Nếu dữ liệu đã thay đổi, cần adapter/reconciliation hoặc roll-forward.

## 31. Observability và timeline quyết định

Mỗi lần chuyển bước cần lưu:
- Change ID/incident ID.
- Version/artifact digest.
- Config/feature flag revision.
- Traffic cohort và tỷ lệ.
- Timestamp bắt đầu/kết thúc.
- SLI và sample size.
- Data validation result.
- Người quyết định/owner.
- Lý do continue/stop/rollback.
- Kết quả sau thay đổi.

Dashboard migration nên có:
- Legacy vs new request volume.
- Success/error/latency theo version.
- Business completion và duplicate rate.
- Data lag, mismatch, missing/extra record.
- Queue age/DLQ.
- CPU/RAM/DB connections.
- Alert/incident.
- Traffic routing state.
- Current writer/source of truth.
- Decommission dependencies còn mở.

Giữ evidence có thể truy lại. Một ảnh chụp màn hình màu xanh không đủ để chứng minh một lần cutover tài chính an toàn; cần query, sample, audit và thời điểm cụ thể.

## 32. Kiểm tra an ninh trong quá trình chuyển đổi

Giai đoạn dual-run thường mở rộng attack surface vì hai hệ thống, nhiều credential và route cùng tồn tại. Cần:
- Identity riêng cho migration job.
- Least privilege cho đọc/ghi và backfill.
- Encryption in transit/at rest.
- Secret/certificate rotation có kế hoạch.
- Không copy PII sang môi trường không được phép.
- Mask/tokenize test data.
- Audit writer switch và quyền break-glass.
- Kiểm tra webhook/API auth ở đích mới.
- Xóa credential cũ sau khi xác minh không còn consumer.
- Bảo vệ log, trace, dump và archive.

Không chia sẻ một admin credential cho cả legacy và new để tiện chuyển đổi. Quyền tạm thời cần expiry và audit. Một hệ thống cũ có thể ít được bảo trì hơn nhưng vẫn chứa dữ liệu nhạy cảm; giữ nó lâu mà không patch cũng là rủi ro.

## 33. Kiểm thử rollback trước khi cần rollback

Một runbook chưa từng chạy không chứng minh phục hồi được. Trước cutover lớn, diễn tập:
- Deploy phiên bản mới rồi rollback code.
- Rollback khi schema đã expand.
- Xử lý message mới còn trong broker.
- Reconcile dữ liệu sau khi writer đã chuyển.
- Failover DB và xác minh RPO.
- Chuyển route về legacy với DNS/cache/connection pool.
- Roll-forward khi rollback không còn tương thích.
- Khôi phục từ backup hoặc archive.
- Thu hồi secret mà không làm mất khả năng recovery.

Ghi lại thời gian thực, điều kiện thất bại và người thực hiện. Nếu rollback cần một DBA duy nhất, một credential đã hết hạn hoặc một script không có owner, đó là blocker phải xử lý trước khi migration có blast radius lớn.

## 34. Runbook cutover mẫu

~~~markdown
# Runbook: Cutover Checkout sang Orders v2

## Owner và phạm vi
- Incident commander:
- Service owner:
- Data owner:
- Security/platform contact:
- Cohort/region:
- Change ID:

## Pre-flight
1. Xác nhận baseline SLO và traffic.
2. Kiểm tra compatibility matrix.
3. Xác minh backfill và replication lag.
4. Kiểm tra backup/restore evidence.
5. Xác minh writer fencing và idempotency.
6. Xác nhận alert, dashboard, on-call và quyền thao tác.

## Thực hiện
1. Bật shadow và so kết quả.
2. Chuyển cohort nhỏ.
3. Theo dõi SLI, data mismatch và duplicate.
4. Tiếp tục tăng traffic theo ngưỡng đã duyệt.
5. Ghi revision, timestamp và quyết định.

## Stop conditions
- SLO vượt ngưỡng.
- Data correctness mismatch vượt policy.
- Replication lag vượt RPO.
- Security/authorization violation.
- Không đủ capacity hoặc không xác nhận được source of truth.

## Recovery
- Dừng rollout.
- Chọn rollback hay roll-forward theo compatibility.
- Không bật writer cũ khi chưa đồng bộ dữ liệu.
- Reconcile side effects và giao dịch.
- Xác nhận SLO/data correctness.

## Completion
- Cửa sổ xác minh đủ dài.
- Owner xác nhận primary.
- Legacy chuyển read-only theo kế hoạch.
~~~

Runbook thật cần điền lệnh, link dashboard, ngưỡng và owner của tổ chức. Không để các trường quan trọng ở trạng thái trống trước khi thực hiện.

## 35. SQL minh họa kiểm tra thiếu và trùng record

Giả sử hai hệ thống có bảng orders với khóa order_id. Có thể dùng anti-join để tìm record chỉ tồn tại ở một bên:

~~~sql
-- Record có ở legacy nhưng thiếu ở hệ thống mới
SELECT l.order_id
FROM legacy_orders l
LEFT JOIN new_orders n ON n.order_id = l.order_id
WHERE n.order_id IS NULL;

-- Record có ở hệ thống mới nhưng không có ở legacy
SELECT n.order_id
FROM new_orders n
LEFT JOIN legacy_orders l ON l.order_id = n.order_id
WHERE l.order_id IS NULL;

-- Kiểm tra key trùng ở đích
SELECT order_id, COUNT(*) AS copies
FROM new_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

Các query chỉ minh họa. Với dữ liệu lớn, cần partition/time window, index và snapshot/transaction consistency để kết quả không bị lệch vì record đang được ghi đồng thời. Không chạy truy vấn nặng trên production mà không ước lượng tải.

Ngoài count, cần so **business invariant** như amount, currency, status, version, createdAt và tenant. Record cùng order_id nhưng số tiền hoặc trạng thái khác vẫn là mismatch.

## 36. Java: mô hình hóa quyết định cutover

Một service điều phối migration có thể biểu diễn các trạng thái rõ ràng thay vì dùng nhiều boolean rời rạc:

~~~java
enum MigrationPhase {
    PREPARED,
    SHADOW,
    CANARY,
    PRIMARY,
    STABILIZING,
    LEGACY_READ_ONLY,
    DECOMMISSIONED
}

enum RecoveryChoice {
    STOP,
    ROLLBACK,
    ROLL_FORWARD,
    DISASTER_RECOVERY
}

record CutoverEvidence(
    boolean contractCompatible,
    boolean dataValidated,
    boolean sourceOfTruthKnown,
    boolean rollbackTested,
    boolean securityApproved,
    boolean sloHealthy,
    boolean sufficientSample
) {
    boolean canStartCanary() {
        return contractCompatible
            && dataValidated
            && sourceOfTruthKnown
            && rollbackTested
            && securityApproved;
    }

    boolean canPromoteToPrimary() {
        return canStartCanary()
            && sloHealthy
            && sufficientSample;
    }
}
~~~

Đây là mô hình logic minh họa, không phải thay thế approval workflow hoặc policy engine. Trong hệ thống thật, bằng chứng phải được lấy từ pipeline/metric/audit có nguồn, không nhận một boolean do người dùng gửi tùy ý.

### 36.1. Unit test

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class CutoverEvidenceTest {
    @Test
    void canaryRequiresCompatibilityAndRecoveryReadiness() {
        var evidence = new CutoverEvidence(
            true, true, true, false, true, true, true
        );
        assertFalse(evidence.canStartCanary());
    }

    @Test
    void primaryRequiresHealthySloAndEnoughSamples() {
        var evidence = new CutoverEvidence(
            true, true, true, true, true, false, true
        );
        assertTrue(evidence.canStartCanary());
        assertFalse(evidence.canPromoteToPrimary());
    }

    @Test
    void promotionRequiresEveryGate() {
        var evidence = new CutoverEvidence(
            true, true, true, true, true, true, true
        );
        assertTrue(evidence.canPromoteToPrimary());
    }
}
~~~

Một unit test xác nhận logic cổng; nó không xác minh dữ liệu migration, SLO thật hay quyền bảo mật. Những điều đó cần integration/operational verification.

## 37. Chuyển đổi monolith sang microservices theo Strangler pattern

Trong Strangler migration, hệ thống mới thay thế dần từng capability:
- Gateway/proxy định tuyến một số route sang service mới.
- Monolith tiếp tục phục vụ phần chưa chuyển.
- Data ownership được tách từng miền.
- Consumer/API contracts được duy trì trong thời gian coexistence.
- Legacy module chỉ bị bỏ khi traffic, data và dependency đã được chuyển.

Một chiến lược ví dụ:
1. Tách Catalog read API trước vì ít side effect.
2. Shadow so kết quả và canary theo route.
3. Chuyển read traffic.
4. Chuyển write sau khi có source of truth và migration.
5. Tách Order lifecycle.
6. Chuyển Payment sau khi hoàn tất security, idempotency và reconciliation.
7. Decommission module cũ theo từng capability.

Không tách toàn bộ database hoặc mọi route cùng lúc. Một lần chuyển đổi nhỏ có blast radius hẹp giúp học và xây năng lực rollback.

## 38. Migration thay nền tảng hoặc cloud provider

Ngoài code/data, còn có:
- IAM identity và policy.
- Network topology, IP allowlist, private link.
- KMS/encryption key và secret.
- DNS, certificate và load balancing.
- Storage consistency, object versioning.
- Backup format và restore compatibility.
- Monitoring, audit và incident integration.
- Quota, region availability và provider limits.

Tiêu chí cutover cần kiểm tra **không chỉ request thành công** mà cả:
- Data durability và checksum.
- Access control và encryption.
- Backup/restore trên nền tảng mới.
- Latency theo region.
- Egress/cross-region cost.
- DR/failover.
- Khả năng xuất dữ liệu nếu cần chuyển tiếp lần nữa.

Không xóa tài khoản/cluster cũ trước khi backup, audit và nghĩa vụ lưu trữ được chuyển. Một số cloud resource có thời gian xóa hoặc retention không thể khôi phục.

## 39. Migration thay database engine

Khi đổi PostgreSQL sang một engine khác hoặc managed variant, phải xét:
- SQL dialect và behavior.
- Isolation level, locking và transaction.
- Sequence/identity và default.
- Timezone, collation, Unicode và decimal.
- Index, query plan và execution semantics.
- Stored procedure/trigger/function.
- CDC/replication behavior.
- Backup/restore format.
- Connection pooling và failover.
- Extension hoặc tính năng đặc thù.

Một test suite pass không chứng minh mọi query sản xuất tương đương. Cần query inventory, representative workload, shadow read, data checks và performance test.

Rollback database engine có thể rất khó nếu dữ liệu mới đã ghi theo semantics không tương thích. Hãy giữ một **migration window** và xác định rõ khi nào cần roll-forward thay vì quay về engine cũ.

## 40. Migration thay event broker

Khi chuyển Kafka cluster hoặc queue provider:
- Inventory producer/consumer group.
- Map topic/queue, partition và retention.
- Xác định offset/checkpoint mapping.
- Kiểm tra ordering, key, retry và DLQ.
- Đồng bộ message phát sinh trong lúc chuyển.
- So consumer lag và business completion.
- Chạy replay thử trên dữ liệu an toàn.
- Giữ broker cũ ở chế độ đọc đến khi hết retention cần thiết.
- Thu hồi ACL/secret sau khi consumer cuối đã rời.

Một phương án là bridge/replication tạm thời, nhưng bridge cũng cần idempotency, monitoring và cách tránh loop. Không chạy hai bridge ngược chiều nếu chưa thiết kế loop prevention và message identity.

## 41. Ngừng một thành phần cũ: đo cả chi phí và lợi ích

Giữ legacy có thể phát sinh:
- VM/DB/license và network.
- Patch/security updates.
- Backup/retention.
- On-call, alert và incident.
- Kỹ năng/tri thức riêng.
- Rủi ro do phiên bản runtime hết hỗ trợ.
- Confusion về source of truth và owner.

Nhưng tắt quá sớm có thể gây:
- Mất dữ liệu lịch sử.
- Hỏng report/batch theo chu kỳ.
- Không thể phục hồi sau migration.
- Mất bằng chứng audit.
- Không xử lý được client cũ hoặc dispute.

Một quyết định decommission cần so:
- Chi phí duy trì legacy trong thời gian chờ.
- Chi phí archive và restore.
- Rủi ro để hệ thống cũ tiếp tục chạy.
- Rủi ro khi xóa và khả năng phục hồi.
- Hạn pháp lý/contract.
- Năng lực hỗ trợ sau khi tắt.

Mục tiêu là **loại bỏ trách nhiệm thực sự đã kết thúc**, không phải chỉ tắt một VM rồi để lại credential, DNS và database mồ côi.

## 42. Phân biệt rollback ứng dụng, dữ liệu và nghiệp vụ

Một kế hoạch rollback có thể có nhiều lớp:

| Lớp | Ví dụ hành động | Giới hạn |
|---|---|---|
| Traffic | Route về legacy | DNS/cache/connection có độ trễ |
| Application | Deploy image trước | Có thể không đọc schema mới |
| Config/flag | Tắt feature | Không đảo side effect đã phát sinh |
| Database | Restore snapshot hoặc reverse migration | Có thể mất giao dịch sau snapshot |
| Event | Replay hoặc transform | Duplicate/order/schema compatibility |
| Business state | Refund/compensate/reconcile | Không luôn hoàn tác thực tế |
| Identity/network | Restore route/credential | Có thể tạo security exposure |

Đừng ghi runbook chỉ có một dòng “rollback deployment”. Cần biết lớp nào đang được khôi phục, dữ liệu nào đã phát sinh và ai phê duyệt thao tác có tác động nghiệp vụ.

## 43. Quản trị quyết định trong ngày cutover

Trước ngày thực hiện:
- Có change record và phạm vi rõ.
- Người điều phối, owner kỹ thuật và data owner xác nhận.
- Đã thử runbook và rollback.
- Có đủ người trực trong cửa sổ.
- Các phụ thuộc ngoài tổ chức đã sẵn sàng.
- Có status channel và quy tắc truyền thông.
- Có freeze cho thay đổi không liên quan nếu cần.
- Backup/restore và quyền break-glass được kiểm tra.

Trong cutover:
- Một người điều phối quyết định bước tiếp.
- Ghi timestamp, revision, cohort và metric.
- Không chạy thao tác ngoài runbook mà không đánh giá blast radius.
- Dừng khi stop condition chạm ngưỡng.
- Không tăng traffic chỉ vì đã hết thời gian trong lịch.

Sau cutover:
- Xác nhận SLO, business outcome và data integrity.
- Ghi quyết định giữ/rollback/roll-forward.
- Theo dõi ticket và incident.
- Cập nhật source-of-truth registry.
- Giữ legacy theo cửa sổ đã thống nhất.
- Chuyển sang decommission khi có bằng chứng.

## 44. Các anti-pattern khi cutover và decommission

| Anti-pattern | Hậu quả | Cách phòng ngừa |
|---|---|---|
| Deploy mới xong là tắt cũ | Chưa đủ chu kỳ nghiệp vụ, mất đường phục hồi | Stabilization window và checklist |
| Hai hệ thống cùng ghi không có fencing | Split-brain, duplicate, conflict | Một writer có thẩm quyền |
| Shadow request gây side effect | Payment/order/email trùng | Dry-run và external adapter |
| Chỉ so HTTP response | Dữ liệu sai nhưng response giống | Business invariant và reconciliation |
| Rollback code nhưng không xét schema | App cũ lỗi hoặc mất dữ liệu | Expand/contract, compatibility matrix |
| Bỏ consumer cũ chỉ vì traffic thấp | Batch/seasonal client bị phá | Support window và inventory |
| Decommission ngay sau canary | Không có đủ bằng chứng | Full cohort, business cycle và audit |
| Backup chưa thử restore | RPO/RTO không chứng minh được | Recovery drill |
| Xóa DB trước khi chuyển report | Mất dữ liệu hoặc report lỗi | Data owner sign-off |
| Giữ legacy vô hạn | Tăng cost và attack surface | Deadline, owner và exit criteria |
| Tắt route nhưng giữ credential admin | Quyền truy cập còn sót | IAM/secret revocation |
| Không lưu migration timeline | Không audit/điều tra được | Change ID, evidence và timestamp |
| Tăng canary theo giờ cố định | Traffic tăng dù metric xấu | Promotion gate theo bằng chứng |
| Gọi mọi sự cố là rollback | Bỏ qua roll-forward/compensation | Decision tree đã chuẩn bị |
| Xóa log/trace sau cutover | Không điều tra được hậu quả | Retention và archive policy |

## 45. Bài tập thực hành

**Bài A — cutover API:** Legacy phục vụ 100% traffic, service mới đã pass integration test. Hãy lập kế hoạch shadow, canary 1/5/25/50/100%, nêu minimum sample, SLI, data checks và stop conditions.

**Bài B — rollback sau khi ghi dữ liệu mới:** Hệ thống mới đã nhận 20.000 đơn và phát event v2. Bản cũ chỉ hiểu v1. Hãy xác định có thể rollback phần nào, phần nào phải giữ reader mới hoặc roll-forward.

**Bài C — database source of truth:** Một đợt migration đã backfill 99,9% dữ liệu, CDC lag còn 2 phút. Xác định điều kiện cần đạt trước khi chuyển writer và fencing ra sao để tránh hai nguồn ghi.

**Bài D — decommission API:** Access log không có request trong 10 ngày nhưng client có thể chạy theo tháng. Thiết kế support window, partner inventory, notification và bằng chứng không còn consumer.

**Bài E — event broker:** Broker mới nhận message mới, broker cũ còn 5.000 message và 200 message trong DLQ. Xây tiêu chí drain, replay, data validation và ngừng cluster cũ.

**Bài F — RTO/RPO:** RTO 60 phút, RPO 5 phút. Rollback application mất 3 phút nhưng backup cách thời điểm lỗi 30 phút. Phân tích availability và data recovery, đề xuất phương án khác.

**Bài G — data correctness:** New Orders có cùng số record với legacy nhưng một số amount và status khác. Viết các query/invariant để tìm sai lệch, xử lý currency/rounding và xác định owner quyết định.

**Bài H — shadow traffic:** Thiết kế shadow cho Payment API mà không capture hai lần, không phát email, không ghi audit event thật. Nêu cách mock external provider và bảo vệ PII.

**Bài I — source of truth:** Hai service cùng nghĩ mình là writer cho OrderStatus. Đề xuất fencing token, optimistic version, idempotency và quy tắc reconcile.

**Bài J — legacy database:** Hệ thống cũ đã read-only nhưng báo cáo cuối tháng vẫn đọc. Lập lịch decommission và archive, điều kiện restore, retention/legal hold.

**Bài K — rollback vs roll-forward:** Schema mới đã được ghi, API cũ không đọc được. Xây decision tree và runbook để chọn hotfix/adapter/roll-forward, đồng thời giới hạn impact.

**Bài L — migration cloud:** Chuyển một service sang cloud mới. Kiểm tra IAM, KMS, DNS, private network, backup, cost, telemetry, failover và quyền xóa tài nguyên cũ.

## 46. Checklist trước khi bấm chuyển traffic

- [ ] Phạm vi và cohort được xác định.
- [ ] Baseline SLI/SLO và business outcomes được lưu.
- [ ] Contract/schema tương thích với các phiên bản còn hoạt động.
- [ ] Data backfill và incremental sync đạt điều kiện.
- [ ] Source of truth và writer fencing rõ.
- [ ] Shadow/canary không gây duplicate side effect.
- [ ] Capacity mới chịu được traffic và failure scenario.
- [ ] IAM, secret, TLS, network và audit đã xác minh.
- [ ] Dashboard, alert và runbook hoạt động.
- [ ] Rollback và roll-forward đã được diễn tập.
- [ ] RTO/RPO phù hợp với phương án thực.
- [ ] Incident commander, service owner và data owner có mặt.
- [ ] Stop conditions và quyền quyết định đã rõ.
- [ ] Reconciliation và business verification sẵn sàng.
- [ ] Thời điểm và change ID được ghi lại.

## 47. Checklist trước khi ngừng legacy

- [ ] Traffic production đã chuyển theo phạm vi.
- [ ] Client/partner và job định kỳ đã được inventory.
- [ ] Không còn writer hoặc consumer cần legacy.
- [ ] Legacy đã read-only và audit xác nhận.
- [ ] Source of truth mới được data owner xác nhận.
- [ ] Backfill, CDC, DLQ và reconciliation hoàn tất.
- [ ] Event replay/retention được giải quyết.
- [ ] Report, batch, settlement và month-end process đã kiểm tra.
- [ ] Backup/archive đáp ứng retention và restore.
- [ ] Legal hold/privacy deletion được xử lý.
- [ ] Credential, certificate, route và IAM đã có kế hoạch thu hồi.
- [ ] Alert, dashboard, runbook và catalog đã cập nhật.
- [ ] Không còn recovery path phụ thuộc server sắp xóa.
- [ ] Chi phí tiết kiệm và chi phí archive đã được ghi nhận.
- [ ] Owner và phê duyệt decommission được lưu.

## 48. Ghi nhớ

- **Cutover, rollback, roll-forward và decommission là bốn quyết định khác nhau**, cần tiêu chí và owner riêng.
- **Deploy thành công chưa chứng minh chuyển đổi thành công.** Cần SLO, business correctness, data reconciliation và cửa sổ xác minh phù hợp.
- **Source of truth phải rõ theo loại dữ liệu/aggregate**, có fencing để tránh hai writer cùng hoạt động.
- **Shadow traffic phải vô hiệu hóa side effects**, nếu không có thể tạo giao dịch, email hoặc payment trùng.
- **Canary tăng theo bằng chứng và mẫu đủ**, không theo lịch cố định.
- **Rollback phải xét dữ liệu, event và external effects**; khi không còn an toàn, cần roll-forward/compensation.
- **RTO và RPO là hai điều kiện khác nhau**; route về nhanh không bảo đảm dữ liệu không mất.
- **Expand–migrate–contract** giúp phiên bản cũ/mới cùng tồn tại và trì hoãn thay đổi phá hủy đến cuối.
- **Decommission cần chứng minh không còn consumer, batch, report, replay hay nghĩa vụ lưu trữ.**
- **Read-only là một giai đoạn kiểm soát**, không tự đồng nghĩa đã ngừng hoặc có thể xóa.
- **Backup chỉ có giá trị phục hồi khi restore được thử** và dữ liệu đáp ứng chính sách.
- **Quyền, secret, route, certificate và audit** phải được thu hồi/cập nhật khi kết thúc.
- **Chi phí dual-run có thời hạn và owner**; giữ legacy vô hạn tạo chi phí và attack surface.
- **Mọi bước chuyển đổi cần evidence có thể truy lại**, không dựa vào một nhãn xanh hoặc xác nhận miệng.

Một cuộc chuyển đổi kiến trúc thành công không phải là khoảnh khắc hệ thống mới nhận 100% traffic. Đó là khi tổ chức **biết chính xác ai sở hữu dữ liệu và hành vi mới, có thể phục hồi khi điều kiện không đạt, chứng minh các chu kỳ nghiệp vụ đã ổn định, và ngừng thành phần cũ mà không để lại dependency hoặc nghĩa vụ ẩn**.
