# Rollback ứng dụng, roll-forward dữ liệu và giới hạn phục hồi

Một bản phát hành mới có thể làm API chậm, gây lỗi xử lý hoặc tạo kết quả nghiệp vụ sai. Phản ứng quen thuộc là rollback về phiên bản ứng dụng trước. Nhưng nếu phiên bản mới đã thay đổi schema database, ghi dữ liệu theo format mới, phát event mới hoặc thực hiện side effect bên ngoài, đưa code cũ trở lại chưa chắc khôi phục được hệ thống. Ứng dụng cũ có thể không đọc được dữ liệu mới, không hiểu event mới hoặc ghi đè thay đổi hợp lệ đã phát sinh.

**Rollback ứng dụng** là chuyển runtime hoặc traffic về một phiên bản phần mềm trước đó. **Roll-forward dữ liệu** là đưa dữ liệu hoặc schema tiến tới một trạng thái tương thích và hợp lệ bằng migration sửa lỗi, transform hoặc replay có kiểm soát. **Restore** là khôi phục dữ liệu từ backup hoặc point-in-time recovery về một thời điểm trước đó. Ba thao tác có mục tiêu khác nhau và không thể thay thế tùy ý cho nhau.

Bài học này thuộc chương **Phân phối phần mềm** của module **CLOUD_ARCHITECTURE**. Mục tiêu là thiết kế phương án phục hồi sau deployment theo cách bảo vệ dữ liệu và giao dịch, hiểu giới hạn rollback khi state đã thay đổi, chọn giữa rollback, roll-forward và restore, đồng thời tổ chức release pipeline, migration, kiểm chứng và vận hành theo tư duy Well-Architected.

## 1. Code rollback không đồng nghĩa data rollback

Ứng dụng, schema và dữ liệu thay đổi theo thời gian nhưng không nhất thiết có thể quay ngược cùng nhau.

Ví dụ:
- Phiên bản 1 đọc cột phone_number.
- Phiên bản 2 thêm cột phone_e164 và bắt đầu ghi cả hai cột.
- Phiên bản 3 ngừng ghi phone_number và chỉ đọc phone_e164.
- Sau đó phát hiện phiên bản 3 lỗi và muốn quay về phiên bản 1.

Nếu dữ liệu mới chỉ được ghi vào phone_e164, phiên bản 1 có thể đọc phone_number rỗng hoặc đã bị xóa. Rollback code không làm dữ liệu tự xuất hiện lại.

Tương tự, một release có thể:
- Đổi enum hoặc JSON payload trong database.
- Phát event schema mới cho consumer.
- Thực hiện migration xóa hoặc gộp cột.
- Gửi email, payment request, webhook hoặc notification.
- Tạo file đã transform hoặc ghi object version mới.
- Thay đổi cache key, session format hoặc token claims.
- Cập nhật model/configuration mà phiên bản cũ không hiểu.

~~~mermaid
flowchart TB
    R1["Release N<br/>Old application"] --> D1[("Database schema/data N")]
    R2["Release N+1<br/>New application"] --> M["Migration / new writes"]
    M --> D2[("Database schema/data N+1")]
    D2 --> Q{"Rollback app N safe?"}
    Q -->|"Compatible"| R1
    Q -->|"Incompatible"| F["Forward-fix / transform / restore"]
    F --> D3[("Compatible corrected data")]
    D3 --> R1
~~~

Một kế hoạch release phải đánh giá ít nhất bốn chiều:
1. **Application compatibility:** code cũ có chạy với dependency và schema hiện tại không?
2. **Data compatibility:** dữ liệu mới có thể được code cũ đọc và cập nhật an toàn không?
3. **External side effects:** giao dịch đã gửi ra ngoài có thể đảo ngược không?
4. **Operational state:** cache, queue, session, feature flag và config có tương thích không?

## 2. Phân biệt rollback, roll-forward, restore và replay

| Hành động | Điều thay đổi | Khi thường dùng | Giới hạn |
|---|---|---|---|
| Application rollback | Code/image/traffic về version trước | Regression do code/config mới | Không tự đảo schema, data hoặc side effect |
| Roll-forward | Sửa schema/data/code tiến lên trạng thái hợp lệ | Migration đã chạy, rollback nguy hiểm | Cần migration/test/approval chính xác |
| Backup restore | Khôi phục dữ liệu từ bản backup | Corruption, accidental deletion, disaster | Có thể mất write sau recovery point |
| Point-in-time recovery (PITR) | Khôi phục database tới thời điểm xác định | Cần quay về trước thao tác lỗi | Có downtime/cutover và phải xử lý giao dịch sau mốc |
| Event replay | Tái xử lý event để dựng trạng thái | Rebuild projection hoặc bù dữ liệu | Duplicate và side effect nếu không idempotent |
| Compensating transaction | Tạo thao tác nghiệp vụ bù | Side effect không thể xóa lịch sử | Không phải mọi hành động đều đảo ngược được |
| Forward-fix | Phát hành bản sửa tiếp theo | Lỗi có thể sửa trong version mới | Cần kiểm soát blast radius và data integrity |

Rollback là thao tác trên phiên bản. Restore là thao tác trên dữ liệu. Roll-forward là cách sửa trạng thái hiện tại. Replay và compensation là kỹ thuật phục hồi theo luồng nghiệp vụ.

Không chọn restore chỉ vì rollback code thất bại. Restore có thể xóa các giao dịch hợp lệ phát sinh sau thời điểm backup. Cần xác định impact và recovery point trước.

## 3. Xác định phạm vi và mức độ sự cố trước khi phục hồi

Trước hành động, phân loại failure:
- **Code regression:** logic mới sai nhưng schema/data vẫn tương thích.
- **Configuration regression:** feature flag, env, policy hoặc routing sai.
- **Schema migration failure:** migration lỗi giữa chừng hoặc tạo schema không tương thích.
- **Data corruption:** dữ liệu bị ghi sai hoặc xóa nhầm.
- **External side effect:** payment, email, webhook hoặc event đã phát.
- **Dependency failure:** database, queue, identity, network hoặc third-party lỗi.
- **Security incident:** dữ liệu bị truy cập/sửa trái phép; yêu cầu containment và evidence preservation.
- **Capacity/performance regression:** bản release mới dùng tài nguyên vượt dự kiến.

Mỗi loại có cách phục hồi khác nhau. Với security compromise, rollback ứng dụng có thể đưa code sạch trở lại nhưng không sửa credential đã lộ hoặc persistence. Với data corruption, forward-fix code có thể ngăn lỗi mới nhưng không tự sửa record đã sai.

### 3.1. Triage checklist

1. Dịch vụ hoặc workflow nào bị ảnh hưởng?
2. Bắt đầu từ deployment/config/migration nào?
3. Có lỗi ở code path, schema, data, event hay external dependency?
4. Data nào đã bị ghi, xóa hoặc transform?
5. Có giao dịch đang chạy hoặc queue chưa xử lý không?
6. Phiên bản trước có tương thích với schema/data hiện tại không?
7. Có side effect đã gửi ra ngoài không?
8. Có thể dừng traffic/write hoặc degrade chức năng không?
9. Recovery objective là gì: availability, consistency, data loss?
10. Cần preservation/audit trước khi thay đổi hệ thống không?

Không bắt đầu rollback khi chưa biết migration đã chạy đến đâu. Có migration chạy theo batch, có migration transaction atomic, và có migration đã commit một phần. Phải kiểm tra migration history và trạng thái thực tế.

## 4. Thiết kế migration tương thích ngược

Một chiến lược quan trọng là duy trì tương thích giữa nhiều phiên bản ứng dụng trong một khoảng thời gian. Điều này cho phép rolling deployment, canary và rollback code mà không cần đảo schema ngay lập tức.

### 4.1. Expand-contract pattern

**Expand** thêm cấu trúc mới nhưng vẫn giữ cấu trúc cũ để phiên bản hiện tại và phiên bản mới cùng hoạt động. **Migrate** chuyển dữ liệu hoặc traffic dần sang cách mới. **Contract** loại bỏ cấu trúc cũ sau khi mọi consumer đã chuyển đổi và rollback window đóng.

~~~mermaid
flowchart LR
    E["1. Expand<br/>Add new column/table"] --> D["2. Dual-read/write<br/>Backfill and validate"]
    D --> S["3. Switch consumers<br/>Read new structure"]
    S --> W["4. Stop legacy writes"]
    W --> C["5. Contract<br/>Remove old structure"]
~~~

Ví dụ đổi cột phone_number thành phone_e164:

**Giai đoạn 1 — Expand**
- Thêm phone_e164 nullable.
- Giữ phone_number.
- Code cũ vẫn đọc/ghi phone_number.
- Code mới có thể ghi cả hai theo một logic nhất quán.

**Giai đoạn 2 — Backfill**
- Chuyển dữ liệu cũ sang phone_e164 theo batch.
- Có checkpoint, retry và metric tiến độ.
- Kiểm tra parse/normalization và record không hợp lệ.
- Không chạy một transaction khổng lồ nếu table lớn.

**Giai đoạn 3 — Switch reads**
- Deploy code đọc phone_e164.
- Có thể tiếp tục dual-write trong compatibility window.
- So sánh giá trị hai cột và phát hiện mismatch.
- Rollback code vẫn đọc được phone_number.

**Giai đoạn 4 — Stop legacy writes**
- Sau khi tất cả phiên bản cũ đã hết traffic, dừng ghi phone_number.
- Theo dõi một khoảng thời gian đủ dài.
- Xác nhận mọi job, report và consumer đã chuyển.

**Giai đoạn 5 — Contract**
- Chỉ khi không còn consumer cũ và rollback window đã đóng, mới xóa phone_number.
- Đây là thay đổi khó đảo ngược; cần backup, approval và maintenance/online migration plan.

### 4.2. Vì sao cần compatibility window?

Rolling deployment có thể đồng thời chạy version N và N+1. Autoscaling hoặc rollback cũng có thể khởi chạy lại version N. Consumer batch và worker có thể được deploy chậm hơn API. Vì thế, schema phải hỗ trợ các version đang tồn tại, không chỉ version mới nhất.

Compatibility window cần tính tới:
- Thời gian deploy toàn fleet.
- Thời gian worker/cron job được cập nhật.
- Queue backlog và message retention.
- Autoscaling/scale-to-zero có thể khởi tạo image cũ.
- Rollback window và thời gian phát hiện lỗi.
- Consumer bên ngoài hoặc partner API.

## 5. Migration có thể reversible đến đâu?

Không phải migration nào cũng đảo ngược an toàn.

| Migration | Khả năng đảo ngược | Lý do |
|---|---|---|
| Add nullable column | Thường dễ hơn | Có thể giữ cột cũ, chưa mất dữ liệu |
| Add new table/index | Có thể rollback schema nếu chưa có dependency | Cần kiểm tra lock/impact và consumer |
| Add enum value | Có thể khó xóa | Record đã dùng value mới có thể không được code cũ hiểu |
| Rename column | Không an toàn nếu app version cũ còn chạy | Cần compatibility layer hoặc add-copy-switch |
| Drop column/table | Khó hoặc không thể đảo nếu không có backup | Dữ liệu đã bị loại bỏ |
| Change type with lossy conversion | Có thể mất thông tin | Giá trị cũ không khôi phục chính xác |
| Merge/split records | Cần mapping và reconciliation | Quan hệ cũ có thể không còn đầy đủ |
| Re-encrypt/re-key | Phụ thuộc key/version | Không giải mã được nếu key cũ mất |
| Delete object/file | Chỉ phục hồi nếu versioning/backup còn | Có thể không có bản cũ |
| Send payment/email/webhook | Không thể rollback bằng code | Side effect đã xảy ra bên ngoài |

Một migration script có lệnh down không chứng minh data rollback an toàn. Lệnh down cần được kiểm tra với dữ liệu production-like, quy mô thật và các trạng thái edge case. Nếu migration có tính lossy, không nên gọi nó là reversible.

### 5.1. Destructive migration

Trước khi drop/overwrite:
- Xác định mọi consumer.
- Backup hoặc snapshot phù hợp.
- Kiểm tra restore và key access.
- Lưu dữ liệu cần giữ hoặc mapping.
- Chạy kiểm tra row count/checksum/invariant.
- Có approval.
- Định nghĩa điểm không thể quay lại.
- Đóng rollback window một cách có chủ đích.

Không dùng destructive schema change cùng deployment code trong một bước nếu chưa có cách phục hồi và xác minh.

## 6. Quyết định rollback ứng dụng có an toàn không?

Trước khi chuyển về version cũ, xác minh:

| Câu hỏi | Nếu không đạt |
|---|---|
| Version cũ có chạy với schema hiện tại? | Không rollback code; forward-fix hoặc compatibility migration |
| Version cũ hiểu event/message mới? | Giữ consumer mới hoặc transform/replay message |
| Dữ liệu mới có thể đọc/ghi bởi version cũ mà không mất thông tin? | Không cho version cũ ghi vào dataset đó |
| Cache/session/token còn tương thích? | Invalidate/translate có kiểm soát hoặc deploy compatibility layer |
| Side effect đã phát có thể xử lý? | Reconcile/compensate; không giả định rollback |
| Có artifact/config/secret phù hợp cho version cũ? | Chuẩn bị lại runtime trước khi chuyển traffic |
| Rollback có thể làm mất fix bảo mật? | Ưu tiên forward-fix hoặc bản cũ đã vá |
| Có thể canary và quan sát sau rollback? | Thiết kế progressive traffic và stop criteria |

Nếu chỉ code regression, schema tương thích, rollback thường là đường ngắn để khôi phục. Nếu migration đã phá compatibility, forward-fix hoặc khôi phục dữ liệu có thể an toàn hơn.

## 7. Blue-green, canary và rollback traffic

Deployment strategy ảnh hưởng đến tốc độ và blast radius của rollback.

### 7.1. Blue-green deployment

Hai môi trường cùng tồn tại:
- Blue là phiên bản đang phục vụ.
- Green là phiên bản mới được triển khai và kiểm tra.
- Traffic chuyển từ Blue sang Green sau readiness checks.
- Nếu lỗi, traffic có thể chuyển về Blue nhanh chóng.

Ưu điểm là rollback traffic nhanh nếu cả hai phiên bản tương thích với data và dependency. Nhưng blue-green không tạo bản sao database độc lập an toàn một cách tự động. Nếu Green đã ghi schema không tương thích hoặc thực hiện side effect, quay traffic về Blue vẫn nguy hiểm.

### 7.2. Canary rollout

Chuyển một phần nhỏ traffic sang phiên bản mới, theo dõi SLI/SLO và business metrics trước khi tăng tỷ lệ.

~~~mermaid
flowchart LR
    U["User traffic"] --> R["Traffic router"]
    R --> OLD["Version N"]
    R --> NEW["Version N+1<br/>Canary 5%"]
    NEW --> M["Metrics / error / business checks"]
    M --> D{"Healthy?"}
    D -->|"Yes"| G["Increase traffic gradually"]
    D -->|"No"| B["Stop rollout / route back"]
~~~

Canary giúp giảm blast radius nhưng phải lưu ý:
- 5% traffic có thể không đại diện cho tenant/region quan trọng.
- Migration có thể đã ảnh hưởng toàn database dù traffic canary nhỏ.
- Background worker có thể chạy 100% dù API chỉ nhận 5%.
- Event consumer mới có thể xử lý mọi event ngay cả khi API chưa tăng traffic.
- Rollback traffic không đảo những write đã phát sinh.

### 7.3. Rolling deployment

Từng instance được thay dần. Trong thời gian này nhiều version cùng hoạt động. Do đó, API, schema, cache, event và session phải tương thích giữa các phiên bản trong rollout window.

Cần readiness/liveness, graceful shutdown, max unavailable, surge capacity và kiểm tra version distribution. Nếu old/new version không tương thích, rolling deployment có thể gây lỗi ngay cả khi từng version chạy riêng lẻ đều tốt.

## 8. Roll-forward và forward-fix

Roll-forward phù hợp khi hệ thống đã nhận dữ liệu/schema mới hoặc rollback gây rủi ro lớn.

Các dạng:
- **Code forward-fix:** phát hành bản sửa kế tiếp, giữ schema hiện tại.
- **Compatibility patch:** thêm adapter hoặc logic để version cũ/mới cùng đọc được.
- **Data transform forward:** chuẩn hóa record sai sang format đúng.
- **Schema migration forward:** thêm cột/index/table hoặc thay đổi tương thích để khắc phục.
- **Event compensation:** phát event bù hoặc command sửa trạng thái downstream.
- **Config/feature flag change:** tắt đường code lỗi mà không cần redeploy toàn bộ nếu flag được thiết kế sẵn.

Một forward-fix nên:
1. Ngăn phát sinh thêm lỗi.
2. Xác định dữ liệu đã bị ảnh hưởng.
3. Giữ nguyên evidence và snapshot cần thiết.
4. Thiết kế migration idempotent và resumable.
5. Thử trên bản sao dữ liệu đại diện.
6. Kiểm tra invariant và kết quả transform.
7. Deploy theo canary/controlled rollout.
8. Theo dõi dữ liệu và business outcomes.
9. Reconcile phần đã xử lý trước đó.
10. Ghi change/incident và điều kiện kết thúc.

Không chạy script sửa dữ liệu trực tiếp trên production mà không có dry-run, checkpoint, backup và cách resume/rollback phù hợp.

## 9. Database restore và point-in-time recovery

Khi dữ liệu bị corruption hoặc xóa nhầm, restore/PITR có thể cần thiết. Tuy nhiên, restore thường tạo ra một database ở thời điểm trước, không tự kết hợp các giao dịch hợp lệ phát sinh sau thời điểm đó.

~~~mermaid
flowchart LR
    T0["Last known good backup"] --> LOG["Transaction logs / WAL"]
    LOG --> PITR["Replay to selected time T"]
    PITR --> DB["Recovered database"]
    DB --> V["Validate and reconcile"]
    V --> CUT["Controlled cutover"]
~~~

Một quy trình PITR cần:
- Xác định thời điểm bắt đầu corruption hoặc thao tác sai.
- Chọn recovery point trước thời điểm đó.
- Kiểm tra backup chain và transaction log/WAL đầy đủ.
- Restore vào môi trường cô lập.
- Chạy integrity checks và business queries.
- So sánh các giao dịch phát sinh sau recovery point.
- Quyết định replay, import hoặc compensate các giao dịch hợp lệ.
- Cutover traffic theo kế hoạch và giữ bản hiện tại để điều tra khi cần.

### 9.1. RPO thực tế của restore

RPO không chỉ phụ thuộc thời điểm backup. Với PITR, khả năng khôi phục còn phụ thuộc tính liên tục của log, retention, replication và khả năng truy cập encryption key. Nếu WAL/binlog bị thiếu hoặc đã hết retention, recovery point có thể không đạt kỳ vọng.

### 9.2. Không restore toàn database khi chỉ một phần bị lỗi nếu có cách hẹp hơn

Có thể:
- Restore vào database tạm rồi export lại bảng/record bị ảnh hưởng.
- Khôi phục một partition/object prefix.
- Rebuild projection từ event log.
- Dùng audit log hoặc CDC để xác định thay đổi.
- Bù giao dịch theo business operation.

Selective recovery giảm lượng giao dịch hợp lệ phải xử lý lại nhưng tăng độ phức tạp và cần hiểu quan hệ dữ liệu.

## 10. Dữ liệu sau migration và compatibility của consumer

Application có thể tương thích với database nhưng không tương thích với event hoặc API của service khác.

### 10.1. Event schema evolution

Khi đổi message schema:
- Ưu tiên thêm field optional có default rõ ràng.
- Không đổi type hoặc semantics field hiện có nếu consumer cũ còn dùng.
- Giữ schema version và event ID.
- Consumer phải bỏ qua field không biết nếu contract cho phép.
- Producer có thể dual-publish trong migration window khi cần.
- Consumer được nâng cấp trước khi producer phát schema breaking.
- Replay cần idempotent và có policy cho event cũ.

Ví dụ thêm booking_source vào BookingCreated event thường tương thích hơn việc đổi booking_id từ string sang object. Nếu event mới đã nằm trong queue, rollback consumer cũ có thể thất bại khi deserialize hoặc diễn giải sai.

### 10.2. Queue backlog và retry

Khi release mới ghi message theo format mới:
- Giữ consumer tương thích hoặc dừng phát event mới.
- Không purge queue chỉ để làm sạch lỗi.
- Đưa poison message vào DLQ có kiểm soát.
- Replay sau khi sửa consumer và xác minh idempotency.
- Theo dõi age, retry count và duplicate rate.

Purge queue có thể xóa công việc hợp lệ; replay không idempotent có thể gửi email/payment/webhook trùng.

## 11. Side effects và compensating transactions

Một thao tác nghiệp vụ đã xảy ra ở hệ thống ngoài không thể bị đảo bằng cách deploy code cũ.

Ví dụ:
- Payment provider đã capture tiền.
- Email confirmation đã gửi.
- Webhook đã được đối tác nhận.
- Reservation đã được đối tác hoặc người dùng khác nhìn thấy.
- File đã được tải xuống.
- Notification đã gửi push tới thiết bị.

Có thể cần **compensating transaction**: một thao tác nghiệp vụ mới để bù kết quả trước, ví dụ refund payment hoặc cancel booking. Compensation không xóa lịch sử; nó tạo một giao dịch khác có audit và trạng thái riêng.

Cần thiết kế:
- Idempotency key theo business operation.
- Transaction/outbox pattern.
- Provider reference và reconciliation.
- Retry policy có giới hạn.
- Saga state machine và compensation step.
- Manual review cho trạng thái không chắc chắn.

Không tự động refund chỉ vì ứng dụng nhận timeout. Provider có thể đã capture nhưng response bị mất. Tra cứu trạng thái theo reference trước khi gửi compensation.

## 12. Feature flags như một lớp rollback hành vi

Feature flag cho phép tắt một chức năng hoặc đường xử lý mà không cần thay image ngay lập tức. Có thể hữu ích khi:
- Model/ranking mới gây lỗi.
- Một integration bên ngoài không ổn định.
- Một workflow mới cần dừng tạm.
- Traffic cần chuyển về logic cũ.

Nhưng flag cũng là production configuration và có rủi ro:
- Flag có thể được cache lâu hoặc áp dụng không đồng nhất.
- Code nhánh cũ có thể không còn được kiểm thử.
- Flag không đảo database migration hoặc side effect đã xảy ra.
- Nhiều flag tích lũy gây combinatorial complexity.
- Flag global có thể tác động mọi tenant.

Mỗi flag nên có owner, purpose, default, scope, expiry/review date, audit trail và test cho cả hai trạng thái. Flag emergency cần được kiểm soát quyền và ghi lại thay đổi.

## 13. Session, cache và token compatibility

Rollback ứng dụng có thể thất bại ở tầng state tạm dù database chưa đổi.

Ví dụ:
- Phiên bản mới serialize session theo cấu trúc mới.
- Cache key đổi prefix hoặc payload.
- JWT claims mới được thêm thành bắt buộc.
- Refresh token được rotate theo policy mới.
- Worker lưu checkpoint có format khác.

Biện pháp:
- Dùng versioned cache/session format.
- Code có thể đọc cả format hiện tại và trước đó trong compatibility window.
- Không yêu cầu version cũ hiểu claim bắt buộc mới nếu chưa có migration.
- Cache có thể invalidate nếu rebuild an toàn, nhưng phải đánh giá cold-start load.
- Session migration có fallback hoặc buộc re-auth có thông báo.
- Giữ token signing/verification key overlap theo rotation policy, không rollback key tùy tiện.

Không dùng cache flush làm cách chữa mọi lỗi deployment. Cache có thể đang chứa state nghiệp vụ hoặc việc flush đồng loạt gây stampede lên database.

## 14. Artifact, configuration và infrastructure compatibility

Rollback chỉ hoạt động nếu artifact và môi trường cần thiết còn sẵn sàng.

Chuẩn bị:
- Container image hoặc package phiên bản trước được lưu immutable.
- Image digest, signature, SBOM/provenance và runtime dependency.
- Config revision đã biết tốt (last-known-good).
- Secret reference/version phù hợp, không copy secret tùy tiện.
- Database migration history và compatibility matrix.
- IaC version và provider version nếu hạ tầng cần thay đổi.
- Feature flag state và routing policy.
- Certificate/trust bundle tương thích.
- Quyền deploy/rollback và pipeline độc lập.

Không rollback IaC bằng cách áp dụng một commit cũ một cách mù quáng. Infrastructure có thể đã thay đổi theo cách không tương thích hoặc chứa resource mới được tạo sau đó. Review plan, state và dependency trước khi thay đổi resource production.

### 14.1. Last-known-good không phải bản cũ bất kỳ

Một release đã chạy tốt trong quá khứ chưa chắc là lựa chọn tốt hiện tại. Nó có thể:
- Có lỗ hổng bảo mật đã biết.
- Không tương thích schema/API hiện tại.
- Dùng secret/certificate đã hết hạn.
- Không hỗ trợ data format mới.
- Thiếu policy hoặc dependency đã được nâng cấp.

Cần duy trì danh sách version đã được xác minh tương thích, không chỉ lưu image cũ.

## 15. Rollback và forward-fix theo tình huống

| Tình huống | Phản ứng thường cân nhắc | Vì sao |
|---|---|---|
| API code regression, chưa đổi schema | Rollback app | Nhanh và dữ liệu còn tương thích |
| Feature mới gây lỗi, flag độc lập | Tắt flag | Giảm tác động nhanh, không cần redeploy |
| Migration expand đã chạy, code mới lỗi | Có thể rollback app | Schema vẫn hỗ trợ version cũ |
| Contract migration đã drop cột | Forward-fix/compatibility migration | Version cũ không còn đủ dữ liệu |
| Data transform sai một phần | Stop writer, snapshot, forward repair hoặc selective restore | Tránh rollback ghi đè dữ liệu hợp lệ |
| External payment đã capture | Reconcile/compensate | Side effect không thể xóa bằng code |
| Event schema mới đã vào queue | Consumer compatibility/transform/replay | Giữ event và tránh mất/duplicate |
| Secret/credential bị lộ | Revoke/rotate và deploy sạch | Rollback code không thu hồi credential |
| Database corruption lan rộng | PITR/restore và reconciliation | Cần khôi phục dữ liệu đúng |
| Security exploit ở release mới | Contain, rollback bản đã vá hoặc forward-fix | Không đưa lại artifact dễ bị khai thác |

Đây là ma trận định hướng; lựa chọn cuối cần phụ thuộc phạm vi ảnh hưởng và data semantics.

## 16. Observability và quyết định kết thúc phục hồi

Trong rollback/roll-forward, theo dõi cả sức khỏe kỹ thuật và kết quả nghiệp vụ.

### 16.1. Kỹ thuật

- Deployment version và traffic split.
- Request rate, p50/p95/p99, error rate và timeout.
- Database migration status, lock, replication lag và connection pool.
- Queue depth, oldest age, retries và DLQ.
- Cache hit/miss, eviction và warm-up.
- Resource saturation và autoscaling.
- Feature flag/config revision.
- External provider latency, quota và response status.

### 16.2. Dữ liệu và nghiệp vụ

- Số booking/payment state hợp lệ.
- Duplicate hoặc orphan transaction.
- Count/checksum sau transform.
- Event publish/consume gap.
- File/object availability và checksum.
- Tỷ lệ workflow hoàn tất.
- Reconciliation mismatch.
- Side effect compensation pending.
- User/tenant cohort bị ảnh hưởng.

Không coi deployment thành công là incident đã kết thúc. Kết thúc khi service đạt SLO, data invariants được kiểm tra, queue/backlog ổn định, side effect được đối soát và owner chấp nhận trạng thái phục hồi.

## 17. Runbook phục hồi release tham khảo

~~~text
PHASE 0 — TRIAGE
  - Identify release, config, migration and affected user journeys.
  - Freeze risky rollout and capture current versions.
  - Determine whether data/schema/external side effects changed.
  - Preserve logs, snapshots and relevant evidence.

PHASE 1 — CHOOSE RECOVERY PATH
  - Check old application compatibility with current schema/data/events.
  - If compatible, prepare application rollback.
  - If incompatible, stop writes or isolate affected workflow.
  - Choose forward-fix, data repair, compensation or PITR as needed.

PHASE 2 — PROTECT DATA
  - Confirm current source of truth and writer.
  - Take a verified snapshot where appropriate.
  - Record transaction/event positions and affected scope.
  - Check backup, key access and restore path.

PHASE 3 — EXECUTE
  - Roll back traffic/code, or deploy a forward-fix.
  - Run migration/data transform in bounded, resumable batches.
  - Keep operations idempotent and checkpoint progress.
  - Reconcile external provider and event side effects.

PHASE 4 — VERIFY
  - Check SLO, user journeys and business invariants.
  - Verify schema, row counts/checksums and queue status.
  - Check duplicate, orphan and pending compensation.
  - Confirm security, config and artifact versions.

PHASE 5 — CLOSE
  - Restore normal release controls.
  - Record incident timeline and data impact.
  - Remove temporary flags/access only after validation.
  - Update compatibility matrix, tests and runbook.
~~~

Runbook cần gắn lệnh/command thực tế với database, orchestrator và deployment platform cụ thể; mỗi thao tác có expected result, owner và stop condition. Không dùng một lệnh chung cho mọi cloud/database.

## 18. Đánh đổi theo Well-Architected

| Khía cạnh | Thiết kế tốt | Rủi ro cần kiểm soát | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Compatibility window, backup/PITR, canary và forward recovery | Rollback không tương thích, data loss, restore kéo dài | Rollback drill, restore test, reconciliation |
| **Bảo mật** | Artifact sạch, credential rotation, audit và evidence | Rollback đưa lại lỗ hổng, secret cũ hoặc policy yếu | Image provenance, IAM audit, key rotation |
| **Hiệu quả hiệu năng** | Cutover có kiểm soát, batch migration và warm-up | Restore load, cache stampede, lock hoặc migration lag | p95/p99, DB load, queue age |
| **Tối ưu chi phí** | Chỉ giữ artifact/backup cần thiết và chọn repair hẹp | Backup/retention quá lớn, duplicate environment | Recovery cost, storage lifecycle |
| **Vận hành xuất sắc** | Runbook, ownership, rollback criteria, postmortem | Phụ thuộc người biết thao tác thủ công, thiếu rehearsals | Drill success, MTTR, action items |
| **Bền vững** | Tránh rebuild/restore toàn bộ khi sửa được phạm vi nhỏ | Compute/transfer dư thừa, replay hoặc reprocessing vô ích | Resource utilization, data transfer, replay volume |

Các đánh đổi quan trọng:
- Rollback nhanh có thể giảm downtime nhưng nguy hiểm nếu data đã tiến tới format mới.
- Forward-fix tránh đảo dữ liệu nhưng cần confidence và test tốt.
- PITR phục hồi điểm nhất quán nhưng có thể loại bỏ giao dịch hợp lệ sau recovery point.
- Expand-contract kéo dài compatibility nhưng tăng thời gian duy trì code/schema kép.
- Canary giảm blast radius nhưng không cô lập migration toàn database.
- Dual-write giúp chuyển đổi dần nhưng có thể tạo mismatch và cần reconciliation.
- Backup dày hơn giảm RPO tiềm năng nhưng tăng chi phí, retention và kiểm soát key.

## 19. Quy trình thiết kế release recovery

1. **Phân loại release:** code, config, schema, data, event, infrastructure và side effect.
2. **Xác định compatibility matrix:** các version app/worker/consumer và schema có thể cùng tồn tại.
3. **Chọn migration pattern:** expand-contract, online migration, batch backfill hoặc maintenance window.
4. **Định nghĩa rollback boundary:** thời điểm nào code còn rollback được; migration nào là irreversible.
5. **Bảo vệ data:** snapshot/backup, PITR, transaction log retention và key access.
6. **Thiết kế forward-fix:** idempotency, checkpoint, validation và resumability.
7. **Kiểm soát side effect:** outbox, idempotency, provider reference và compensation.
8. **Chuẩn bị artifact/config:** last-known-good đã được kiểm tra tương thích và bảo mật.
9. **Thiết lập canary/feature flag:** stop criteria, routing và ownership.
10. **Định nghĩa SLI/business invariant:** cách biết hệ thống thực sự đã phục hồi.
11. **Viết runbook:** triage, decision, execute, verify, stop và rollback.
12. **Diễn tập:** code rollback, migration failure, PITR, event replay và compensation.
13. **Đóng recovery window:** chỉ contract/drop dữ liệu cũ sau khi consumer và rollback window kết thúc.
14. **Review sau release/incident:** cập nhật test, migration policy và recovery assumptions.

### Checklist trước production release

| Hạng mục | PASS khi |
|---|---|
| Version compatibility | Version trước chạy được với schema/data trong rollback window |
| Migration | Expand/contract hoặc maintenance strategy rõ |
| Reversibility | Migration destructive được đánh dấu và có recovery path |
| Backup/PITR | Recovery point, retention và key access đã kiểm tra |
| Artifact | Last-known-good image/config còn sẵn sàng và được kiểm soát |
| Event/API | Producer/consumer compatibility được xác minh |
| Side effects | Idempotency, reconciliation và compensation rõ |
| Feature flags | Owner, scope, default, expiry và audit |
| Rollback criteria | Có SLI, business impact và người quyết định |
| Roll-forward | Có forward-fix/data repair đã thử nghiệm |
| Validation | Có data invariant, smoke test và SLO check |
| Runbook | Đã review và diễn tập phù hợp criticality |

## 20. ADR minh họa — Đổi schema Booking khi phát hành phiên bản mới

> **Bối cảnh:** Booking API đang lưu phone_number và cần chuẩn hóa sang phone_e164. Release mới đồng thời thay đổi response API và gửi BookingUpdated event với schema mới.
>
> **Phương án A:** Deploy code mới và rename/drop phone_number trong cùng một migration. Đơn giản về mặt thay đổi nhưng version cũ không thể rollback nếu release gặp lỗi sau khi migration hoàn tất.
>
> **Phương án B:** Expand-contract. Thêm phone_e164, dual-write, backfill, chuyển read, nâng cấp consumer và chỉ drop phone_number sau khi đóng compatibility window.
>
> **Quyết định minh họa:** Chọn B. Triển khai schema expand trước; sau đó phát hành API/worker đọc cấu trúc mới nhưng vẫn duy trì ghi tương thích. Event schema thêm field optional và consumer cũ bỏ qua field chưa biết theo contract.
>
> **Rollback:** Trong compatibility window, có thể route về application version cũ vì phone_number vẫn còn và được duy trì. Không rollback consumer nếu queue đã chứa message không tương thích.
>
> **Roll-forward:** Nếu dual-write có mismatch, dừng contract phase, sửa transform và backfill lại các record có checkpoint; không drop cột cũ.
>
> **Validation:** So sánh record count, checksum/normalized value, invalid phone rate, event consumer lag, booking success và API latency.
>
> **Điều kiện contract:** Tất cả API/worker/consumer đã chuyển, không còn read/write legacy, reconciliation pass và rollback window kết thúc.

## 21. Bài tập thực hành: release lỗi sau khi schema đã thay đổi

Booking Platform vừa triển khai phiên bản 5.4:
- Thêm cột payment_status_v2 và backfill từ payment_status.
- API mới chỉ đọc payment_status_v2.
- Worker mới phát PaymentCaptured event schema version 2.
- Một phần payment đã được provider capture.
- Sau 15 phút, tỷ lệ confirmation lỗi tăng mạnh.
- Phiên bản 5.3 vẫn chạy được trong artifact registry nhưng chỉ đọc payment_status và hiểu event schema version 1.
- Một số consumer chưa được nâng cấp.

**Yêu cầu:**
1. Xác định có thể rollback API 5.3 ngay không và cần kiểm tra điều kiện nào.
2. Xác định trạng thái migration và khả năng dữ liệu mới đã được ghi riêng vào cột v2.
3. Thiết kế cách giữ PaymentCaptured v2 mà consumer cũ không bị crash hoặc hiểu sai.
4. Quyết định rollback code, forward-fix hay kết hợp.
5. Đối soát payment đã capture nhưng confirmation thất bại.
6. Xử lý event queue, retry và DLQ không tạo duplicate side effect.
7. Xác định điều kiện nào mới cho phép drop payment_status cũ.
8. Viết runbook và tiêu chí kết thúc phục hồi.

### Hướng giải quyết

- Không route toàn bộ API về 5.3 trước khi xác minh cột payment_status còn được dual-write và mọi record cần thiết đã có giá trị tương thích.
- Nếu schema vẫn ở giai đoạn expand và cột cũ còn đủ dữ liệu, có thể rollback API theo canary; worker/consumer phải được đánh giá riêng.
- Nếu provider đã capture nhưng response/confirmation lỗi, tra cứu provider transaction reference trước khi retry capture hoặc refund.
- Giữ event v2 trong durable queue; nâng consumer hỗ trợ cả version 1 và 2, hoặc transform message có versioning và không đổi event ID. Không purge queue.
- Forward-fix có thể sửa mapping/confirmation trong API 5.4.x trong khi giữ schema expand; chọn cách ít rủi ro nhất theo dữ liệu hiện tại.
- Đối soát provider settlement, database payment state, outbox event, consumer offset và DLQ. Dùng idempotency key để tránh capture/notification lặp.
- Chỉ drop payment_status sau khi mọi app/worker/consumer đã chuyển, cột cũ không còn được đọc/ghi, reconciliation pass và rollback window đóng.
- Kết thúc khi booking/payment workflow đạt SLO, không còn trạng thái không rõ, queue backlog/DLQ được xử lý, data invariants pass và owner phê duyệt.

### Câu hỏi tự kiểm tra

1. Vì sao rollback code không tự khôi phục database?
2. Rollback, roll-forward, restore và replay khác nhau thế nào?
3. Expand-contract giúp giữ tương thích giữa phiên bản cũ và mới ra sao?
4. Vì sao drop column là một điểm khó quay lại?
5. Khi nào forward-fix an toàn hơn PITR?
6. Vì sao PITR có thể làm mất giao dịch hợp lệ sau recovery point?
7. Canary traffic có cô lập được migration toàn database không?
8. Làm thế nào xử lý event schema mới đã nằm trong queue khi rollback consumer?
9. Vì sao payment timeout không đồng nghĩa provider chưa capture?
10. Compensation khác rollback như thế nào?
11. Feature flag có thể đảo ngược những gì và không đảo được những gì?
12. Điều kiện nào cho phép contract phase xóa cấu trúc legacy?

Khả năng phục hồi release phụ thuộc vào việc hiểu điều gì đã thay đổi và điều gì có thể đảo ngược. **Rollback ứng dụng chỉ an toàn khi code cũ còn tương thích với schema, dữ liệu, event và dependency hiện tại.** Khi dữ liệu hoặc side effect đã tiến về phía trước, thường cần forward-fix, migration tương thích, reconciliation hoặc compensation; restore/PITR chỉ nên dùng khi đã xác định recovery point và cách giữ lại giao dịch hợp lệ. Thiết kế expand-contract, backup đã kiểm thử, idempotency, canary và runbook giúp nhóm phục hồi mà không biến một lỗi release thành sự cố mất dữ liệu lớn hơn.
