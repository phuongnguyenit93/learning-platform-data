# Khôi phục từ dữ liệu xóa nhầm và hạn chế ghi đè dữ liệu đúng

Một lệnh xóa sai trong database NoSQL có thể kết thúc chỉ sau vài mili giây nhưng làm mất hàng triệu documents, items, keys hoặc rows. Khi phát hiện sự cố, phản xạ phổ biến là lấy snapshot gần nhất rồi restore thẳng vào production. Cách này có thể làm các bản ghi vừa bị xóa xuất hiện trở lại, **nhưng đồng thời ghi đè những thay đổi hợp lệ mà người dùng thực hiện sau thời điểm snapshot**.

Trong một ứng dụng cho thuê, lúc 10:05 một batch job vô tình xóa các booking có trạng thái `CONFIRMED`. Lúc 10:12 những booking khác vẫn được khách hàng cập nhật hợp lệ. Nếu phục hồi nguyên database từ bản sao lúc 10:00, hệ có thể lấy lại booking bị xóa nhưng lại đánh mất thông tin thanh toán, thay đổi ngày ở hoặc hủy đặt chỗ hợp lệ từ 10:00 đến nay. Một sự cố xóa nhầm đã trở thành sự cố **ghi đè dữ liệu đúng**.

Bài học thuộc chương **Sao lưu và phục hồi** trong module **Database No SQL**. Nội dung tập trung vào cách nhận diện phạm vi xóa nhầm, bảo toàn bằng chứng, dùng backup/point-in-time recovery (PITR) để tạo **nguồn dữ liệu phục hồi cô lập**, đối chiếu theo khóa và phiên bản, áp dụng thay đổi có điều kiện, bảo vệ cập nhật mới, khôi phục CDC/search/cache đúng thứ tự, kiểm chứng business invariants và diễn tập quy trình. Các ví dụ liên hệ MongoDB, Cassandra, DynamoDB, Redis, dữ liệu dẫn xuất và ứng dụng Java.

> **Nguyên tắc cốt lõi:** **Restore không đồng nghĩa overwrite.** Với một sự cố xóa nhầm có cập nhật hợp lệ xảy ra sau đó, mặc định hãy **phục hồi ra môi trường riêng, lập danh sách bản ghi thật sự cần cứu, rồi merge có điều kiện**. Chỉ chọn thay thế toàn bộ production khi đã có quyết định nghiệp vụ rõ về việc bỏ các thay đổi sau recovery point hoặc có cơ chế replay/reconcile chúng.

## 1. Mục tiêu học tập

Sau bài này, người học cần có khả năng:

1. Phân biệt xóa nhầm với xóa hợp lệ, TTL hết hạn, tombstone, lỗi đọc và lỗi index.
2. Xây timeline sự cố theo commit/event positions, không suy luận chỉ từ đồng hồ.
3. Chọn recovery source: snapshot, PITR, backup, audit log, change stream hoặc source of truth khác.
4. Phân biệt restore toàn bộ, restore có chọn lọc, replay events và rebuild projection.
5. Giữ các writes hợp lệ xảy ra sau recovery point.
6. Dùng unique constraints, conditional writes, optimistic concurrency và version guards để tránh overwrite.
7. Tạo dry-run plan và kiểm thay đổi trước khi áp dụng.
8. Thiết kế quy trình xác minh dữ liệu và business invariants.
9. Lập runbook cho MongoDB, Cassandra, DynamoDB, Redis và các hệ dẫn xuất.
10. Đo RPO/RTO, thời gian phục hồi và tổ chức diễn tập an toàn.

## 2. “Dữ liệu biến mất” không nhất thiết là đã bị xóa vật lý

Một document không xuất hiện trong kết quả có thể do:

| Tình huống | Dấu hiệu | Cách điều tra |
| --- | --- | --- |
| `deleteOne/deleteMany` sai | Có delete events/audit | Xác định IDs và thời điểm |
| TTL/expiration | Bản ghi hết hạn theo chính sách | Kiểm TTL field, clock, expiry policy |
| Soft delete | `deletedAt`/`isDeleted=true` | Kiểm filter của query |
| Tombstone trong LSM | Row bị đánh dấu xóa | Kiểm semantics timestamp/compaction |
| Sai partition key | Query nhắm nhầm shard/tenant | Kiểm key và routing |
| Replica lag | Một bản sao chưa theo kịp | Kiểm consistency/replication |
| Search/CDC lag | Index chưa thấy dữ liệu | Đọc source authority |
| Access control | Principal không còn quyền đọc | Kiểm IAM/roles/tenant |
| Schema/query regression | Query không match field mới | Xem query shape/index |
| Restore hoặc import lỗi | Dữ liệu bị thay/thiếu sau job | Kiểm job history và manifest |

**Bước đầu tiên là chứng minh dữ liệu bị mất ở nguồn có thẩm quyền**, thay vì vội thực hiện restore. Một search index trả thiếu kết quả có thể chỉ cần rebuild từ source.

## 3. Xác định nguồn có thẩm quyền

Một hệ phân tán có thể có:

~~~text
Booking Authority (NoSQL)
    |
    +--> CDC → Search index
    |
    +--> Redis cache
    |
    +--> Analytics projection
    |
    +--> Outbox/event stream
~~~

Với từng đối tượng, hỏi:

- **Authoritative record** nằm ở đâu?
- Search/cache là bản sao được phép tái tạo hay chứa dữ liệu duy nhất?
- Có event ledger/audit log độc lập không?
- Có thể tái dựng state từ events đã commit không?
- Nếu restore nguồn, những projections nào cần replay hoặc rebuild?

Nếu cache chỉ là bản sao, đừng lấy cache làm nguồn phục hồi khi đã có database authority. Nếu Redis thực sự là primary store, phải có chính sách durability/backup như một hệ cơ sở dữ liệu chính.

## 4. Timeline xóa nhầm và cập nhật hợp lệ

Xem tình huống minh họa:

~~~text
09:55  Snapshot S0 hoàn thành
10:04  User tạo booking A, version 7
10:05  Batch job vô tình xóa A (delete version 8)
10:08  User cập nhật booking B, version 13
10:12  User tạo booking C hoàn toàn mới
10:20  Nhóm vận hành phát hiện lỗi
10:22  Dừng batch job, bảo vệ retention/logs
10:30  Phục hồi PITR vào cluster cô lập R
10:50  Lập và duyệt recovery plan
11:10  Merge chọn lọc vào production
~~~

Nếu restore toàn bộ production về 10:04:59:

- A có thể được tìm lại.
- B bị quay về phiên bản cũ.
- C có thể biến mất.
- Các phiên làm việc, events và external effects sau 10:04:59 không tự được rollback đồng bộ.

**Recovery point là điểm lấy dữ liệu để cứu, không mặc nhiên là mốc thời gian mà toàn bộ nghiệp vụ phải quay về.**

## 5. Hai bài toán phải giải cùng lúc

### Bài toán A — Khôi phục đủ dữ liệu bị mất

Không bỏ sót bản ghi thuộc **phạm vi xóa nhầm**, giữ đúng fields, types, references và các quan hệ nghiệp vụ cần thiết.

### Bài toán B — Không phá dữ liệu đúng

Không thay thế:

- Bản ghi đã được user cập nhật hợp lệ sau mốc backup.
- Bản ghi đã được tạo lại hợp lệ.
- Bản ghi bị xóa có chủ đích sau sự cố.
- Những thay đổi hợp lệ khác về payment, inventory, status, audit.

Thành công phải thỏa **cả hai**, không chỉ là số lượng documents sau restore tăng trở lại.

## 6. Các bất biến cần viết ra trước thao tác

Ví dụ với một booking authority:

~~~text
Invariant I1:
  Mỗi reservationId có tối đa một bản ghi authoritative.

Invariant I2:
  Một yêu cầu phục hồi chỉ được tạo hiệu ứng một lần.

Invariant I3:
  Không hạ aggregate version của booking đang sống.

Invariant I4:
  Không phục hồi booking được xóa hợp lệ bởi người dùng.

Invariant I5:
  Tồn kho/tiền/điểm thưởng không được cộng lại chỉ
  vì một bản ghi lịch sử được đưa trở về.

Invariant I6:
  Mọi thao tác cứu dữ liệu có evidence, approval và audit.
~~~

Một thao tác restore có thể làm I1, I3 hoặc I5 sai dù file backup còn nguyên vẹn. **Business invariants phải được xem ngang hàng với bit-level recovery.**

## 7. “Đúng” được xác định bằng lịch sử, không chỉ current value

Giả sử:

~~~text
10:04 A = CONFIRMED, version 7
10:05 A = DELETED, version 8 (do incident)
10:09 A = RECREATED, version 9 (hợp lệ)
~~~

Tại thời điểm phục hồi, A đang tồn tại ở version 9. Nếu lấy A version 7 từ backup rồi upsert mù quáng, sẽ **ghi đè bản mới đúng**. Nếu chỉ thấy một ID có trong backup và kết luận “cần phục hồi” cũng sai.

Một phiên bản đủ tin cậy cần có:

- Business key/aggregate identity ổn định.
- Event hoặc state version có semantics rõ.
- Provenance: ai và thao tác nào thay đổi record?
- Deletion reason/source và incident evidence.
- Dấu vết cập nhật hợp lệ sau deletion.

**Bản ghi trong backup là quá khứ; current state có thể chứa thông tin đúng mới hơn.**

## 8. Bước khẩn cấp: containment trước recovery

Khi phát hiện xóa nhầm:

1. Khởi tạo incident theo mức độ ảnh hưởng.
2. Xác định job, credential, query/filter gây xóa.
3. Dừng hoặc cô lập **nguồn gây xóa tiếp**, theo quy trình được duyệt.
4. Hạn chế thay đổi liên quan, nhưng **không freeze toàn bộ production một cách mù quáng**.
5. Lưu job logs, command IDs, query shape, deploy/config versions.
6. Bảo vệ backup/PITR retention và CDC/change-log expiry.
7. Ghi thời điểm phát hiện, vùng ảnh hưởng, affected key ranges.
8. Chọn incident commander, database owner và business approver.

### Vì sao không vội “đóng băng mọi write”?

Một write freeze rộng có thể làm hỏng booking, payments và customer operations đang hợp lệ. Cần đánh giá **freeze theo tenant, collection, partition, job hoặc hành động cụ thể**, kèm SLO/correctness impact.

## 9. Bảo vệ bằng chứng khỏi bị ghi đè hoặc hết hạn

Các nguồn evidence có vòng đời khác nhau:

| Nguồn | Rủi ro khi chậm xử lý |
| --- | --- |
| PITR log window | Recovery point trôi ra khỏi retention |
| CDC/change stream | Resume position hết hạn |
| Audit logs | Rotation/retention xóa mất |
| Backup snapshots | Lifecycle policy xóa bản cũ |
| Application traces | Sampling và short retention |
| Object store exports | Cleanup jobs xóa tạm |
| Tombstones/MVCC history | Compaction/garbage collection |
| User-facing evidence | Có thể thiếu timestamps/IDs |

Ưu tiên **bảo vệ thông tin bằng tính năng chính thức của provider/DB**, không tự copy secret hoặc dump PII ra máy cá nhân. Khi cần kéo dài retention hoặc tạo snapshot bổ sung, cân nhắc capacity/cost và an toàn.

## 10. Recovery Point Objective và Recovery Time Objective

- **RPO:** lượng dữ liệu tối đa tổ chức chấp nhận mất trong tình huống phục hồi, thường diễn đạt theo thời gian.
- **RTO:** thời gian mục tiêu để dịch vụ được khôi phục đến trạng thái sử dụng được.

Với xóa nhầm, cần thêm:

- **Affected record recovery completeness:** tỷ lệ records cần cứu được xác nhận.
- **Legitimate write preservation:** số updates hợp lệ sau recovery point được giữ.
- **Reconciliation lag:** bao lâu để projections/cache/events đúng lại?
- **Data correctness:** số invariants bị vi phạm sau phục hồi.

Một restore hoàn thành trong 5 phút nhưng xóa sạch các writes hợp lệ của 30 phút vừa qua **không phải phục hồi thành công**.

## 11. Khôi phục toàn bộ và khôi phục có chọn lọc

| Phương án | Lợi ích | Rủi ro |
| --- | --- | --- |
| Restore đè toàn bộ production | Có vẻ nhanh, đơn giản | Ghi đè updates đúng sau mốc |
| Restore vào cluster/table cô lập | Không đụng production ban đầu | Cần extra storage/time |
| Selective copy theo IDs | Phạm vi chính xác hơn | Cần xác định affected set |
| PITR + CDC replay | Có thể tái dựng state nhiều thời điểm | Ordering, duplicates, gaps |
| Field-level patch | Giữ fields đúng của current | Khó resolve conflicts |
| Event-sourced recomputation | Bảo toàn history nếu log đầy đủ | Phụ thuộc event fidelity |
| Rebuild search/cache | Phù hợp với derived stores | Không cứu được authority đã mất |

**Mặc định có lợi nhất về an toàn là isolated restore + selective reconciliation**, nhưng phải đánh giá RTO, kích thước dữ liệu, feature hỗ trợ và tính nhất quán của recovery point.

## 12. Tại sao isolated restore quan trọng?

~~~text
          Production Authority
                 |
         (không overwrite)
                 |
                 +----------------------+
                                        |
      PITR/Snapshot                     |
           |                            |
           v                            |
    Isolated Recovery DB                |
           |                            |
           v                            |
       Compare / Diff <-----------------+
           |
           v
     Approved Recovery Plan
           |
           v
    Conditional Merge into Production
~~~

Ưu điểm:

- Có thể kiểm nguồn backup, schema và index trước khi làm production.
- Có thể chạy diff, sampling và business checks.
- Có thể đổi recovery point nếu phát hiện mốc sai.
- Giảm nguy cơ vô tình ghi đè.
- Có thể lập manifest và tính trước số writes cần thực hiện.

### Cô lập thực sự là gì?

Recovery cluster cần identity/network khác production theo policy, ACL tối thiểu, secrets riêng, không tự kích hoạt consumer/webhook/job gửi email/payment. Một bản restore có trigger/workers tự chạy và phát side effects có thể tạo **sự cố thứ hai**.

## 13. Snapshot và PITR có những giới hạn gì?

### Snapshot

Là ảnh dữ liệu tại một mốc hoặc tập mốc được hệ hỗ trợ. Tính nhất quán giữa shards/collections/tables phụ thuộc engine và công cụ snapshot.

### Point-in-time recovery

Khôi phục trạng thái tới một thời điểm/position trong recovery window bằng snapshot và logs theo semantics của dịch vụ.

### Cần xác nhận

1. Mốc PITR có độ chính xác và múi giờ nào?
2. Có thể restore sang **new cluster/table** không?
3. Dữ liệu giữa shards có consistent cut không?
4. Role, index, TTL, streams, network settings được restore thế nào?
5. Có bao gồm các writes đã ACK trước mốc đó theo durability contract không?
6. Backup/PITR window còn bao lâu?
7. Restore cần bao nhiêu disk, network, thời gian?
8. Source/target có khác version hoặc feature flag không?

**Tên tính năng “PITR” không tự chứng minh mọi write xuyên nhiều databases được phục hồi nguyên tử theo một mốc tuyệt đối.**

## 14. Chọn recovery point trước sự cố xóa

Giả sử log:

~~~text
10:04:56Z good update
10:04:59Z good insert
10:05:00Z destructive job begins
10:05:07Z multiple deletes
~~~

Mốc nguồn phục hồi có thể chọn **ngay trước delete đầu tiên đã commit**, với độ phân giải được DB/PITR cho phép.

### Cảnh giác

- Job có thể xóa theo batches trong vài phút.
- Nhiều source partitions/shards có log ordering riêng.
- Đồng hồ của app và DB có thể lệch.
- Commit time khác thời điểm request bắt đầu.
- Một batch good write có thể commit xen giữa các bad deletes.

Vì vậy “10:05” chỉ là dấu mốc sơ bộ; cần dựa vào database commit positions, operation IDs hoặc audit evidence khi có thể.

## 15. Lập danh sách affected keys chính xác

Một affected-set manifest có thể gồm:

~~~json
{
  "incidentId": "INC-518",
  "source": "booking.reservations",
  "deleteJobId": "job-20261114-42",
  "recoveryPoint": "before-first-bad-delete",
  "expectedAffectedCount": 3,
  "keys": [
    "reservation:R101",
    "reservation:R102",
    "reservation:R103"
  ],
  "evidence": [
    "approved-audit-reference",
    "change-log-position"
  ]
}
~~~

Không coi danh sách này đáng tin chỉ vì script tạo ra nó. Cần so:

- Delete events thực sự commit.
- Query filter/tenant/range của job.
- Audit/operation counts.
- Backup/PITR recovered keys.
- Cases mà người dùng xóa hợp lệ cùng thời gian.

Khi tập khóa rất lớn, manifest có thể chia partitions và lưu hash/checksum; luôn có owner và provenance.

## 16. Phân loại từng bản ghi trước khi merge

| Recovery copy | Production hiện tại | Diễn giải | Hành động mặc định |
| --- | --- | --- | --- |
| Có bản cũ | Tombstone đúng incident, chưa thay đổi | Có thể cần phục hồi | Candidate |
| Có bản cũ | Bản mới hợp lệ version cao hơn | Không được overwrite | Skip/reconcile |
| Có bản cũ | Đã xóa hợp lệ sau incident | Không được tự hồi sinh | Skip/manual review |
| Có bản cũ | Bản hiện tại khác dữ liệu cũ | Conflict | Manual/domain merge |
| Không có trong recovery copy | Có bản hiện tại | Tạo sau snapshot | Giữ nguyên |
| Có bản cũ | Không có record/tombstone evidence | Outcome chưa đủ chắc | Quarantine/review |
| Có bản cũ | Chỉ thiếu một field | Có thể patch field | Conditional field repair |

**Không có record ở current không tự chứng minh “đã bị xóa nhầm”.** Có thể do TTL, xóa hợp lệ, di chuyển tenant, key đổi hoặc ứng dụng chưa bao giờ tạo record đó ở authority.

## 17. Vì sao phiên bản và tombstone giúp an toàn?

Một model có thể lưu:

~~~json
{
  "id": "R101",
  "version": 8,
  "state": "DELETED",
  "deletion": {
    "operationId": "job-20261114-42",
    "reason": "incident"
  }
}
~~~

Tại thời điểm phục hồi, candidate ở version 7 từ recovery DB. Nếu current vẫn là tombstone version 8 thuộc incident, có thể áp **một transition mới**:

~~~text
R101 v7 ACTIVE
    → R101 v8 DELETED (accidental)
    → R101 v9 RESTORED (compensating action)
~~~

Không nên ghi đè bằng document cũ giữ nguyên `version=7`. Version nên tiếp tục tăng theo protocol của ứng dụng, để downstream consumers biết đây là event mới và không lẫn với quá khứ.

## 18. Compare-and-set (CAS) ngăn cạnh tranh với user update

Một race:

~~~text
Recovery worker reads current version 8 (deleted).
User re-creates booking, current version becomes 9.
Recovery worker blindly puts backup version 7.
~~~

Kết quả: ghi đè bản mới của người dùng.

CAS/conditional update:

~~~text
UPDATE only if:
  id=R101
  AND current.version=8
  AND current.state=DELETED
  AND current.deletion.operationId=incident-job

SET:
  state=RESTORED
  selected recovered fields
  version=9
  restorationId=INC-518:R101
~~~

Nếu user đã tạo version 9, condition không match và recovery **không được overwrite**. Worker phải ghi conflict để review hoặc rebuild plan từ state mới.

## 19. Unique insert cho bản ghi đang vắng mặt

Nhiều hệ hard-delete xóa hẳn record và không giữ tombstone ở lớp ứng dụng.

~~~text
Recovery sees key R101 missing.
Another service creates R101.
Recovery attempts unconditional put R101.
~~~

Nếu dùng put mặc định có semantics upsert/replace, bản mới bị ghi đè. Cần **insert-if-not-exists** bằng unique key/conditional write thích hợp để tránh overwrite.

### Nhưng thiếu tombstone tạo vấn đề khác

Insert-if-not-exists chỉ chống trùng **với bản ghi đang tồn tại**; không chứng minh absence là do incident. Cần log/evidence xác định key thuộc sự cố và chưa có xóa hợp lệ sau đó. Nếu thiếu evidence, đưa vào danh sách cần xử lý thủ công.

## 20. So sánh version: không suy từ timestamp đơn lẻ

Giả sử hai writers:

~~~text
Writer A clock = 10:05:10
Writer B clock = 10:05:03 (skew 7 seconds)
~~~

Nếu chọn bản “mới hơn” theo client-side wall-clock timestamps, có thể chọn sai.

Ưu tiên:

- Monotonic aggregate version do authority quản lý.
- Database ETag/revision/CAS token.
- Commit sequence/stream offset trong phạm vi được bảo đảm.
- Causal information/event ordering theo aggregate.

Nếu DB có LWW theo timestamp, cần hiểu clock/timestamp semantics của **đúng engine**. Không tự tuyên bố timestamp lớn hơn luôn là thay đổi nghiệp vụ đúng hơn.

## 21. Cần phân biệt update, delete và restore là các events

~~~text
Event E1: BookingCreated(R101,v7)
Event E2: BookingDeleted(R101,v8,reason=INC)
Event E3: BookingRestored(R101,v9,reason=INC-518)
~~~

Một restoration hợp lệ là **một thay đổi mới có nguyên nhân và audit trail**, không phải âm thầm thay state về quá khứ khiến các consumers khác không biết.

### Những điều event restore cần ghi

- Stable `restorationId` cho idempotency.
- Aggregate ID và expected previous version.
- Reason/incident/approver.
- Restored fields/state source.
- New version/commit position.
- Cách consumers tránh side effects lặp.

Một `BookingRestored` không nên tự kích hoạt thanh toán lần nữa nếu payment đã được thực hiện trước sự cố.

## 22. Phục hồi sai có thể tạo side effect kép

Một document booking được khôi phục có thể bị downstream hiểu thành “booking vừa mới tạo”:

~~~text
Recovery inserts booking R101
    |
    +→ Outbox/CDC
    +→ Loyalty worker: award points again?
    +→ Email worker: send confirmation again?
    +→ Inventory worker: reserve one more slot?
~~~

Hệ phải phân biệt **compensating restore** và **new booking intent**, kèm idempotency/business event identity.

### Phương án

- Event type riêng như `BookingRestored`.
- Consumer contract rõ khi thấy restoration.
- Ledger theo business key chống double award/capture.
- Quarantine hoặc gate side-effect consumers trong isolated recovery environment.
- Reconciliation với payment/inventory/notifications trước khi bật traffic bình thường.

## 23. Restore toàn bộ: khi nào vẫn có thể phù hợp?

Có tình huống có thể chọn full restore:

- Toàn bộ dữ liệu sau một recovery point được xác định là không hợp lệ.
- Hệ đã ngừng writes và doanh nghiệp **chấp nhận** mất interval đã tính.
- Có event replay để tái tạo những writes hợp lệ sau điểm restore.
- Restore vào secondary, đồng bộ rồi thực hiện controlled cutover.

### Không được làm

~~~text
Restore old backup OVER production
without identifying valid post-backup writes
and without rollback/reconciliation plan
~~~

Một restore tool hỗ trợ `--drop`, `overwrite`, `replace` hoặc xóa target trước khi copy có thể phá current state. Luôn hiểu semantics của tham số trước khi chạy.

## 24. Khoảng thời gian bị ảnh hưởng không đồng nghĩa toàn bộ thời gian đã mất

Trong ví dụ:

~~~text
09:55 Snapshot exists
10:05 Accident happens
10:20 Detection
10:50 Recovered copy ready
~~~

Một restore nguyên cluster về 09:55 mất toàn bộ legitimate changes từ 09:55 đến 10:50. Nhưng selective recovery có thể chỉ bù **những keys bị xóa do incident**, còn các writes khác giữ nguyên.

Điều này cho thấy RPO truyền thống của full restore không mô tả hết **logical data correction**. Cần bổ sung **record-level recovery scope và legitimacy checks**.

## 25. Schema thay đổi giữa snapshot và hiện tại

Một backup cũ có:

~~~json
{
  "reservationId": "R101",
  "totalPrice": 250000
}
~~~

Schema mới dùng:

~~~json
{
  "reservationId": "R101",
  "amountMinor": 250000,
  "currency": "VND",
  "schemaVersion": 3
}
~~~

Blind copy document cũ có thể làm application hiện tại không đọc được hoặc đổi ý nghĩa tiền tệ.

### Recovery phải xử lý

1. Biết schemaVersion tại recovery point.
2. Migration/normalization sang schema hiện tại.
3. Bảo toàn type/precision/null/missing fields.
4. Không vô tình reset metadata mới.
5. Test domain validation trước merge.
6. Có checksum/record-level comparison sau chuyển đổi.

**Restore dữ liệu đúng thời điểm nhưng sai schema vẫn là khôi phục lỗi.**

## 26. Field-level patch: cứu trường bị xóa mà giữ những trường mới

Một lỗi update chỉ xóa trường `deliveryAddress`:

~~~text
Backup v10:
  address = "Old address"
  phone   = "123"

Current v12:
  address = missing (accidental)
  phone   = "456" (legitimate user update)
~~~

Nếu replace cả document v10, số điện thoại `456` bị ghi đè về `123`.

Phương án tốt hơn có thể là **patch đúng trường `address`** và bảo vệ bằng condition trên current revision, sau khi xác minh không có thao tác đổi địa chỉ hợp lệ sau sự cố.

### Điều kiện

Một patch field-level có thể vẫn sai nếu người dùng chủ ý xóa địa chỉ hoặc cập nhật field cùng lúc. **Field selection và business authorization** quan trọng như version guard.

## 27. Các loại conflict khi merge

| Conflict | Ví dụ | Cách xử lý |
| --- | --- | --- |
| Re-created record | Backup R101 cũ; current R101 mới | Skip và review |
| Legitimate update | Current version cao hơn backup | Giữ current, nếu cần patch có điều kiện |
| Legitimate delete | User hủy booking sau incident | Không hồi sinh |
| Concurrent edit | User update khi recovery worker chạy | CAS conflict, retry re-evaluation |
| Schema conflict | Backup field cũ | Migrate trước merge |
| External side effect | Payment đã capture | Không replay capture |
| Cross-record invariant | Inventory cần đồng bộ | Transaction/compensation theo authority |
| Missing provenance | Không biết vì sao absent | Quarantine, không tự điền |

**Không lấy last-write-wins mặc định làm business conflict resolution** nếu đúng/sai không thể xác định từ thứ tự đến.

## 28. Thiết kế dry-run manifest

Mỗi candidate nên ghi:

~~~json
{
  "incidentId": "INC-518",
  "businessKey": "reservation:R101",
  "recoverySource": "PITR-copy-before-delete",
  "backupVersion": 7,
  "currentVersion": 8,
  "currentState": "DELETED",
  "deleteOperationId": "job-20261114-42",
  "plannedAction": "CONDITIONAL_RESTORE",
  "expectedCondition": {
    "version": 8,
    "state": "DELETED"
  },
  "newVersion": 9,
  "restorationId": "INC-518:R101",
  "approval": "review-required"
}
~~~

Tập manifest cần là **immutable artifact có kiểm soát và hash/provenance**. Không đưa secrets hoặc full PII vào file điều phối nếu không cần. Có thể lưu document hashes và dẫn tới recovery source được bảo vệ.

## 29. Dry-run phải kiểm gì?

Trước merge:

1. Tổng candidate IDs và phân bố theo tenant/collection.
2. Có bao nhiêu key thật sự vắng do incident?
3. Bao nhiêu key đã được update/re-created sau deletion?
4. Bao nhiêu legitimate deletes có nguy cơ hồi sinh?
5. Bao nhiêu records có schema/type incompatibilities?
6. Bao nhiêu reference/invariant violations nếu phục hồi?
7. Bao nhiêu writes và IOPS/throughput cần cho apply?
8. Ai duyệt và có ngưỡng dừng khi conflicts tăng?

Ví dụ dry-run report:

~~~text
Manifest candidates:     50,000
Safe conditional restore:47,200
Current version changed:  1,900
Legitimate delete:          500
Missing provenance:         400
Total:                    50,000
~~~

**47.200 là số ứng viên tại thời điểm dry-run**, không được xem là 47.200 writes bảo đảm thành công. Một user có thể thay record trước lúc actual apply; CAS sẽ phải đánh giá lại.

## 30. Apply theo batch nhỏ và có khả năng dừng

~~~text
Approved recovery plan
     |
     v
Canary 10 records
     |
     v
Check CAS results + invariants + CDC
     |
     v
Batch 100–1000 records
     |
     v
Monitor errors/throughput/conflicts
     |
     v
Continue or pause
~~~

Batch size phải theo capacity, impact và backend limits; những con số chỉ là gợi ý thử nghiệm.

### Những metric cần theo dõi

- Applied, skipped, conflicted, failed counts.
- New vs old versions.
- Rate và backlog.
- DB p95/p99, throttling, compaction.
- CDC/search freshness.
- Side-effect consumer activity.
- Errors per tenant/key range.

Recovery script nên **idempotent**: chạy lại cùng `restorationId` không tạo thêm một hiệu ứng mới.

## 31. Transaction boundary của recovery

Không phải mọi NoSQL hỗ trợ transaction đa record giống nhau. Có thể có:

- Atomic update trên một document/item.
- Conditional put/update trên một key.
- Multi-document/multi-item transaction có giới hạn.
- Batch API không bảo đảm atomicity cả batch.
- Eventual replication hoặc conflict resolution đặc thù.

### Thiết kế phù hợp

Nếu restore một booking cần đồng bộ inventory ledger, outbox và booking state, phải xác định **atomic authority boundary** cho các thay đổi này. Nếu không thể transaction chung, thiết kế workflow bù trừ, idempotency và reconciliation; không gọi một batch best-effort là atomic.

**Tính đúng của recovery phụ thuộc guarantee thực sự của engine, không phụ thuộc tên method “batchWrite”.**

## 32. Ví dụ Java 17: mô phỏng phục hồi có điều kiện

Chương trình dưới đây tự chạy, không kết nối DB thật. Nó minh họa **bảo vệ bản hiện tại** bằng revision và nguyên nhân xóa.

Tạo file `SelectiveRecoveryDemo.java`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public final class SelectiveRecoveryDemo {
    record Record(
            String id,
            long version,
            String value,
            boolean deleted,
            String deleteOperationId) {}

    record Candidate(String id, String recoveredValue,
                     long recoveredVersion,
                     long expectedCurrentVersion,
                     String expectedDeleteOperationId) {}

    enum Outcome {
        RESTORED, SKIPPED_CURRENT_CHANGED,
        SKIPPED_NO_MATCHING_TOMBSTONE
    }

    static Outcome restoreIfUnchanged(
            Map<String, Record> production,
            Candidate candidate) {

        Record current = production.get(candidate.id());

        if (current == null || !current.deleted()
                || !candidate.expectedDeleteOperationId()
                    .equals(current.deleteOperationId())) {
            return Outcome.SKIPPED_NO_MATCHING_TOMBSTONE;
        }
        if (current.version()
                != candidate.expectedCurrentVersion()) {
            return Outcome.SKIPPED_CURRENT_CHANGED;
        }

        production.put(
            candidate.id(),
            new Record(candidate.id(),
                current.version() + 1,
                candidate.recoveredValue(),
                false, null));
        return Outcome.RESTORED;
    }

    public static void main(String[] args) {
        Map<String, Record> production =
                new LinkedHashMap<>();

        // A: accidental delete is still present.
        production.put("A",
            new Record("A", 8, null, true, "bad-job"));

        // B: user already made a legitimate new write.
        production.put("B",
            new Record("B", 13, "new-user-value",
                false, null));

        // C: legitimate delete from another operation.
        production.put("C",
            new Record("C", 14, null, true,
                "user-cancel"));

        Candidate[] candidates = {
            new Candidate("A", "old-valid-A",
                7, 8, "bad-job"),
            new Candidate("B", "old-B",
                12, 12, "bad-job"),
            new Candidate("C", "old-C",
                13, 14, "bad-job")
        };

        for (Candidate candidate : candidates) {
            Outcome outcome =
                restoreIfUnchanged(production, candidate);
            System.out.println(
                candidate.id() + " -> " + outcome);
        }
        System.out.println(
            "A version=" + production.get("A").version());
        System.out.println(
            "B value=" + production.get("B").value());
        System.out.println(
            "C deleted=" + production.get("C").deleted());
    }
}
~~~

Chạy:

~~~bash
javac SelectiveRecoveryDemo.java
java SelectiveRecoveryDemo
~~~

Kết quả dự kiến:

~~~text
A -> RESTORED
B -> SKIPPED_NO_MATCHING_TOMBSTONE
C -> SKIPPED_NO_MATCHING_TOMBSTONE
A version=9
B value=new-user-value
C deleted=true
~~~

### Giới hạn quan trọng

- `Map` trong JVM **không bảo vệ concurrent writes từ processes khác**. Trong production, check + mutation phải là **một atomic conditional operation tại DB**.
- Mã minh họa không dùng `recoveredVersion` để chứng minh lịch sử; evidence phải do audit/recovery workflow cung cấp.
- Không ghi restoration ID bền và không bao gồm cross-document invariants.
- Không có CDC, network, persistence hoặc retry; chỉ thể hiện quyết định logic.

## 33. Java demo không thay được atomic DB write

Đoạn sai về concurrency:

~~~java
// PSEUDOCODE - KHÔNG AN TOÀN
Record current = db.get(id);
if (current.version() == 8) {
    db.put(recoveredRecord);
}
~~~

Giữa `get` và `put`, một user khác có thể ghi version 9. Cần phương thức của database có semantics tương đương:

~~~text
Compare-and-set:
  if current.id = R101 AND current.version = 8
  then set recovered fields AND version = 9
  else return conflict
~~~

Nếu provider/engine không hỗ trợ conditional update cần thiết, không tự mô phỏng bằng application locks với TTL rồi tuyên bố tuyệt đối an toàn. Cân nhắc thay workflow, isolate writes, transaction boundary hoặc append-only corrections.

## 34. MongoDB: phục hồi có chọn lọc thay vì replace toàn collection

Với MongoDB, một workflow tổng quát:

1. Xác định thời gian/keys và availability của backup/PITR.
2. Restore backup sang **cluster/database cô lập** bằng cơ chế đúng deployment.
3. Đọc recovered documents theo `_id` và migration schema nếu cần.
4. Đọc current production state với read concern phù hợp.
5. Classify: matching incident tombstone, updated, recreated, intentionally deleted.
6. Apply conditional updates bằng filter chứa `_id`, `version` và `deleteOperationId`.
7. Kiểm `matchedCount` và audit result.
8. Reconcile change streams và projections.

Một `replaceOne` với chỉ filter `_id` có thể ghi đè record hiện tại. Một `upsert:true` mù quáng có thể vừa hồi sinh xóa hợp lệ vừa tạo duplicate business effect.

### Hard-delete với `deleteMany`

Nếu MongoDB không giữ application tombstones, có thể restore docs với **unique insert** để ngăn ghi đè keys hiện có. Nhưng phải dựa vào audit/change streams để chứng minh key thực sự thuộc incident, và phải đánh giá conflicts do valid delete/recreate.

## 35. MongoDB Java: conditional restore khi có tombstone

Ví dụ với MongoDB Java synchronous driver, giả sử mỗi document có trường `version`, `deleted`, `deleteOperationId`; driver dependency và phiên bản được cấu hình riêng:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.set;
import static com.mongodb.client.model.Updates.unset;

final class BookingRecoveryMongo {
    static boolean restoreOne(
            MongoCollection<Document> bookings,
            String id, long expectedVersion,
            String badOperationId, String recoveredStatus,
            String restorationId) {

        UpdateResult result = bookings.updateOne(
            and(
                eq("_id", id),
                eq("version", expectedVersion),
                eq("deleted", true),
                eq("deleteOperationId", badOperationId)
            ),
            combine(
                set("status", recoveredStatus),
                set("deleted", false),
                set("version", expectedVersion + 1),
                set("restorationId", restorationId),
                unset("deleteOperationId")
            )
        );
        return result.getMatchedCount() == 1;
    }
}
~~~

### Giới hạn của ví dụ

- Đây là thao tác **atomic trên một document** theo MongoDB update semantics, không bảo đảm atomicity của những collections liên quan.
- `id`/`recoveredStatus` chỉ lấy từ manifest **đã được duyệt**, không từ request tùy ý.
- Mã chưa validate schema, field histories, business invariants hoặc idempotent event emission.
- Trường `version` phải do tất cả writers cùng tôn trọng; nếu một write bỏ qua version protocol, guard không còn đủ.
- Cần read/write concerns, TLS, authorization, logs và retries phù hợp deployment.
- Không dùng `upsert:true` ở đoạn này: tombstone không match phải là conflict, không phải chèn mới không kiểm soát.

## 36. MongoDB: insert-if-absent cho hard-delete

Nếu current không có `_id=R101`, một insert có unique `_id` sẽ thất bại khi writer khác đã tạo record cùng ID trước đó. Đây là lớp bảo vệ chống overwrite.

Nhưng cần:

~~~text
Evidence:
  R101 was deleted by job INC-518.

Current state:
  R101 is absent at apply time.

Policy:
  No legitimate delete/re-key after incident.
  Business invariant permits restoration.

Action:
  INSERT new restoration record with traceability
  relying on unique key constraint.
~~~

Nếu concurrent write thắng race, **không dùng fallback replace/upsert**. Ghi conflict và kiểm current.

### Change streams

Change stream có thể hỗ trợ điều tra delete events/resume theo product contract và retention. **Không giả định chỉ dựa vào change stream delete event mà có toàn bộ document trước khi xóa**; cần pre-image capability được bật/hỗ trợ hoặc backup.

## 37. Cassandra: tombstone và timestamp rất quan trọng

Cassandra/wide-column storage có deletion tombstones và timestamp semantics. Một record bị xóa có thể không phục hồi đơn giản bằng cách đưa SSTable cũ quay lại live node.

Những điểm cần lưu ý:

- Tombstone có thể thắng cell cũ theo timestamp/merge rules.
- Nếu viết lại dữ liệu với timestamp **không phù hợp**, bản ghi có thể vẫn bị che hoặc ghi đè một write mới.
- TTL, compaction, repair và tombstone garbage collection ảnh hưởng thời gian/safety.
- Một file SSTable cũ không phải snapshot nhất quán của toàn keyspace khi ứng dụng đang ghi.
- Khôi phục qua bulk load/sstable tools có yêu cầu phiên bản, topology và operational safety riêng.

### Cách làm an toàn về nguyên tắc

1. Phục hồi snapshot/backup trên môi trường cô lập theo tài liệu phiên bản.
2. Lấy affected partition keys/rows và evidence.
3. Kiểm trạng thái hiện tại, timestamps/version ở cấp ứng dụng.
4. Xây compensating writes với protocol version/CAS hoặc logic authority được chấp nhận.
5. Tránh sửa thủ công timestamp để “ép dữ liệu cũ thắng” khi có nguy cơ overwrite legitimate writes.
6. Repair/reconcile theo runbook phù hợp cluster.

**Đừng tự thay `gc_grace_seconds` hoặc nạp SSTables cũ vào production** chỉ để nhìn thấy deleted rows trở lại; có thể gây inconsistency và làm hỏng anti-entropy assumptions.

## 38. Cassandra: LWT/CAS và giới hạn

Nếu dữ liệu nghiệp vụ được bảo vệ bởi bảng/version protocol hỗ trợ lightweight transactions (LWT), recovery có thể dùng conditional write để bảo vệ một trạng thái mong đợi:

~~~sql
-- CQL minh họa: schema phải thực sự có các cột tương ứng.
UPDATE booking_state
SET status = 'RESTORED',
    version = 9
WHERE reservation_id = 'R101'
IF version = 8;
~~~

Kết quả `[applied]=true/false` xác định condition có thắng trong phạm vi LWT hỗ trợ. Đoạn CQL này **không tự chứng minh** bản version 8 là accidental delete, không đồng bộ mọi tables, và không thay được audit/business review.

### Caveat

Cassandra data modeling không mặc định khuyến khích transaction đa partition. Nếu recovery cần thay nhiều tables hoặc materialized views, phải thiết kế idempotent workflow/reconciliation hoặc transaction boundary khác, không suy LWT một row bao trùm toàn nghiệp vụ.

## 39. DynamoDB: PITR restore ra bảng mới

Với DynamoDB, PITR và on-demand backup có restore semantics riêng, thường tạo **bảng mới** thay vì rollback đè dữ liệu hiện hữu. Đây là lợi thế cho việc so sánh và selective recovery.

Workflow:

~~~text
Production table
       |
PITR before accidental deletion
       |
       v
Recovery table (separate)
       |
       v
Read affected keys / transform
       |
       v
Conditional PutItem/UpdateItem to production
       |
       v
Validate + reconcile Streams/indexes
~~~

### Những điều phải kiểm

- Table/index configuration sau restore, capacities và encryption settings.
- IAM, tags, TTL, Streams, auto scaling và regional replication configuration.
- Recovery point chính xác trong retention window.
- Cost cho bảng phục hồi và reads/scans.
- Không tự kích hoạt event processors/schedulers khi dữ liệu phục hồi.

Đừng coi restore sang bảng mới là đồng nghĩa bảng mới có mọi operational setting giống source; kiểm theo documentation của service và snapshot.

## 40. DynamoDB: conditional write chống overwrite

Nếu một hard-deleted item **chắc chắn thuộc incident** và key vẫn absent, có thể dùng conditional put:

~~~text
PutItem recovered item
ConditionExpression:
    attribute_not_exists(pk)
~~~

Với composite key, kiểm uniqueness trên **full primary key** theo semantics của table/condition expression. Nếu item đã tồn tại, condition fail và worker phải review thay vì chuyển thành unconditional update.

### Ví dụ AWS SDK for Java v2

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.dynamodb.model
        .ConditionalCheckFailedException;

final class DynamoRecovery {
    static boolean insertMissingOnly(
            DynamoDbClient db,
            String tableName,
            String pk, String sk,
            String recoveredStatus) {

        PutItemRequest request = PutItemRequest.builder()
            .tableName(tableName)
            .item(Map.of(
                "pk", AttributeValue.builder().s(pk).build(),
                "sk", AttributeValue.builder().s(sk).build(),
                "status", AttributeValue.builder()
                    .s(recoveredStatus).build()))
            .conditionExpression("attribute_not_exists(pk)")
            .build();

        try {
            db.putItem(request);
            return true;
        } catch (ConditionalCheckFailedException conflict) {
            return false;
        }
    }
}
~~~

Đây là skeleton, không phải script production: item thực tế còn version, owner, amounts, audit, restoration ID và các fields bắt buộc; client phải dùng IAM tối thiểu, deadline/retry policy và encryption. **Không catch mọi exception rồi coi là conflict**: timeout có unknown outcome, throttling/network/auth errors cần xử lý riêng. Nếu condition fail, phải đối chiếu current item.

## 41. DynamoDB: version guard trên item đang tồn tại

Nếu có application tombstone:

~~~text
pk=RESERVATION#R101
sk=STATE
version=8
deleted=true
deleteOperationId=job-42
~~~

Một `UpdateItem` với condition gồm `version=8 AND deleted=true AND deleteOperationId=job-42` sẽ bảo vệ update đúng như CAS. Trong transaction nhiều items, dùng transactional API được hỗ trợ nếu invariant thực sự nằm trong scope của nó.

### Streams và Global Tables

Các writes phục hồi có thể xuất hiện trong Streams hoặc được replicate sang regions khác. Cần định nghĩa event type/idempotency và hiểu last-writer/conflict semantics của global replication; **không coi một write được accept ở region A là đã an toàn trong mọi region mà không xét chính sách dịch vụ**.

## 42. Redis: khi nào phải restore và khi nào chỉ rebuild?

Redis thường dùng làm cache:

~~~text
Authoritative Booking DB → Redis Cache
~~~

Nếu Redis keys bị xóa nhưng authority vẫn đúng, thông thường **repopulate cache** từ authority hoặc để cache miss tự rebuild, có kiểm rate limit để tránh stampede.

Nếu Redis là primary datastore, cần backup/persistence recovery theo cấu hình:

- RDB snapshot.
- AOF/rewrite log trong cấu hình phù hợp.
- Replication/failover history.
- TTL/expiration semantics.
- Key namespace và type.

### Cảnh báo với lệnh restore

Một thao tác bulk `FLUSHDB`, `RESTORE ... REPLACE` hoặc nạp snapshot cũ vào production có thể ghi đè keys hiện tại/TTL đúng. Ưu tiên **phục hồi Redis instance cô lập**, trích những keys đã xác minh, rồi apply bằng cơ chế atomic conditional/idempotent phù hợp.

## 43. TTL và expiration: không hồi sinh dữ liệu cố ý hết hạn

Giả sử voucher dùng TTL:

~~~text
Backup: voucher V1 expires at 10:10
Current time: 11:00
~~~

Nếu restore bản cũ mà đặt TTL mới một ngày, voucher đã hết hạn có thể hoạt động lại sai chính sách.

### Cần phân biệt

- Dữ liệu bị xóa nhầm.
- Dữ liệu tự hết hạn hợp lệ.
- Dữ liệu được retention policy yêu cầu phải xóa.
- Dữ liệu đã bị xóa theo yêu cầu privacy của chủ thể.

**Không hồi sinh dữ liệu đã có nghĩa vụ phải xóa**. Recovery có thể cần redaction/skip theo retention/privacy policy dù backup vẫn giữ bytes.

## 44. Search index và projection: phục hồi từ authority

Nếu MongoDB/DynamoDB/Cassandra authority vẫn đúng, nhưng OpenSearch/Elasticsearch index bị xóa nhầm:

~~~text
Authority → Snapshot/export → New search index
          → CDC catch-up → Validate → Alias cutover
~~~

Tạo new index/projection có thể giảm nguy cơ overwrite dữ liệu search phục vụ traffic. Sau khi bắt kịp CDC và xác minh queries/freshness, chuyển alias/routing có kiểm soát.

### Lưu ý

- Nếu chỉ restore index snapshot cũ rồi bỏ qua CDC sau snapshot, dữ liệu vẫn stale.
- Chỉ đếm documents không phát hiện sai nội dung hoặc version.
- Build/index merge tốn disk/network/CPU.
- Delete events hợp lệ sau snapshot phải được replay; không được hồi sinh documents bị xóa theo yêu cầu người dùng.

**Read model có thể rebuild không có nghĩa write authority cũng có thể rebuild từ read model.**

## 45. CDC replay để giữ legitimate writes sau recovery point

Một cách tiếp cận:

~~~text
PITR snapshot at watermark W0
        |
        v
Recovery copy
        |
        +→ Replay good events after W0
        |      (exclude/reverse bad operation carefully)
        |
        v
Reconstructed candidate state at W1
        |
        v
Compare with current authority
        |
        v
Conditional merge
~~~

### Không đơn giản là “bỏ delete event”

Nếu có update hợp lệ sau delete event trên cùng aggregate, việc bỏ delete nhưng giữ update có thể tạo lịch sử khác logic thực tế. Cần domain-aware event reconciliation, idempotency, version/causal ordering và kiểm invariants.

**Replay event không luôn đảo ngược được**: một payment đã capture hoặc email đã gửi không bị undo khi replay database events.

## 46. Dedupe và ordering trong recovery

Giả sử events:

~~~text
E101: created R101 v7
E102: bad-deleted R101 v8
E103: user-restored R101 v9
~~~

Nếu recovery replay E101 sau E103 mà không có version guard, current state bị lùi.

Các cơ chế:

- Event ID để chống duplicate delivery.
- Aggregate version để bảo vệ ordering.
- Gap detection khi thiếu E102/E103.
- Snapshot watermark để nối nguồn.
- Consumer checkpoint sau durable effect.
- Business-intent ID để chống double charge/book.

Một Kafka/stream “exactly-once” configuration không tự bao trùm external NoSQL và mọi side effects. Phải nêu **atomic transaction boundary** của từng kết quả.

## 47. Dữ liệu liên quan phải được đối soát

Khôi phục document booking có thể tác động:

~~~text
Booking R101
    |
    +→ Inventory allocation
    +→ Payment ledger
    +→ Loyalty points
    +→ Notification history
    +→ Search projection
    +→ Analytics event
~~~

Nếu chỉ tăng số bookings, không đồng bộ ledger/inventory, hệ có thể bị oversell hoặc cộng điểm hai lần.

### Đối soát theo identity

- Reservation IDs và status.
- Inventory reserved units theo listing/date.
- Payment intent IDs và captured amounts.
- Loyalty award uniqueness.
- Outbox/consumer checkpoint.
- Source-vs-projection versions.

**So total counts không đủ**: một record bị mất và một record bị nhân đôi có thể khiến tổng không đổi.

## 48. Business correctness khi khôi phục giao dịch tiền

Một khách đã thanh toán và nhận xác nhận có thể không được phép tạo payment mới chỉ vì booking record vừa được restore.

Protocol cần:

1. Không gửi external payment call từ recovered snapshot mặc định.
2. Kiểm payment authority/ledger trước compensation.
3. Dùng stable business idempotency key.
4. Phân biệt create, restore, refund, chargeback.
5. Audit actor/incident và approval cho compensation.
6. Reconcile số tiền theo currency/minor units.

Nếu dữ liệu payment nhạy cảm, backup/recovery cần tuân thủ các chính sách bảo mật và pháp lý; không export toàn bộ secrets/payment details vào recovery report.

## 49. Multi-tenant: phục hồi đúng tenant, không trộn dữ liệu

Một script sai filter:

~~~text
Restore all reservationId starting with "R"
~~~

Trong hệ multi-tenant, cùng reservation ID có thể tồn tại ở hai tenants nếu primary key thực sự là `(tenantId, reservationId)`.

### Điều kiện an toàn

- Affected key phải là **full authoritative key**, không chỉ display ID.
- Manifest có tenant/project/partition scope.
- Identity thực thi chỉ được đọc/ghi phạm vi cần phục hồi.
- Queries và apply filters có tenant condition.
- Audit và business owner kiểm sample cross-tenant.
- Không dùng account super-admin cho mọi thao tác nếu có thể giới hạn.

**Một recovery script có thể trở thành cross-tenant data leak** dù dữ liệu được phục hồi về mặt kỹ thuật.

## 50. Bảo mật môi trường phục hồi

Recovery data thường chứa PII đã bị xóa khỏi production theo yêu cầu hoặc nội dung nhạy cảm lịch sử.

Controls cần:

- Isolated network, không public endpoints.
- Dedicated service identity/least privilege.
- Encryption at rest/in transit.
- Access audit, approver và hạn chế exports.
- Không tự chạy scheduled jobs, CDC consumers, notification workers.
- TTL/cleanup cho recovery artifacts sau incident.
- Redact logs/diffs, dùng hashes khi đủ.
- Policy riêng cho retention, legal hold, privacy deletion.

**Càng nhiều bản sao recovery, càng tăng attack surface và nghĩa vụ bảo vệ dữ liệu.**

## 51. Vai trò trong một cuộc phục hồi

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident commander | Điều phối, quyết định khi nào apply/cutover |
| Database/platform engineer | Backup, PITR, topology, capacity |
| Application/domain owner | Business invariants và conflict resolution |
| Security/privacy | Quyền, logs, retention, compliance |
| Data analyst/QA | Diff, samples, reconciliation |
| SRE/on-call | SLO, dashboards, rollback và communication |
| Provider support | Hỗ trợ chức năng managed theo hợp đồng |

Một tác vụ ghi hàng chục nghìn records nên có **separation of duties**: người tạo plan và người duyệt/giám sát không nhất thiết là một, tùy quy mô tổ chức và rủi ro.

## 52. Quy trình runbook từ phát hiện tới xác minh

~~~text
DETECT
  Missing records / delete audit / SLO signal
       |
       v
CONTAIN
  Stop bad writer; preserve evidence and retention
       |
       v
SCOPE
  Affected keys, tenants, delete operations, timestamps
       |
       v
RESTORE ISOLATED
  PITR/snapshot to protected recovery target
       |
       v
DIFF & REVIEW
  Backup state vs current vs later legitimate events
       |
       v
APPROVE
  Business rules, risk, data privacy, batches
       |
       v
CONDITIONAL APPLY
  Unique insert / CAS / transaction / compensation
       |
       v
RECONCILE
  Authority, ledger, inventory, CDC, search, cache
       |
       v
VERIFY & CLOSE
  SLO, completeness, audit, follow-up, cleanup
~~~

### Runbook không chỉ là danh sách commands

Cần có entry criteria, owner, decision points, pause/stop thresholds, pre/post conditions, evidence links, recovery fallback và cách giao tiếp với người dùng bị ảnh hưởng.

## 53. Tiêu chí pause và rollback trong lúc merge

Một canary batch có thể lộ lỗi mà dry-run chưa thấy.

Đặt ngưỡng dừng trước:

- Conflicts tăng bất thường.
- Documents được cập nhật có version không mong đợi.
- Payment/inventory invariants bị vi phạm.
- Database write latency/throttling tăng mạnh.
- CDC backlog không thể drain.
- Restore operation gây side effects trái kế hoạch.
- Manifest/provenance mismatch hoặc approval thiếu.

### Rollback không phải lúc nào cũng đảo ngược

Nếu recovery đã gửi email hoặc gọi payment API, undo DB không xóa được email hoặc hoàn tác payment. Vì vậy **prevention và canary quan trọng hơn hy vọng rollback**.

## 54. Chứng minh phục hồi thành công

Một acceptance report có thể gồm:

~~~text
Incident ID: INC-518
Affected keys verified: 50,000
Approved restores:      47,200
Conditionally applied:  47,180
Conflicts during apply:     20
Skipped intentionally:   2,800
Invariant violations:        0
Unresolved cases:           20
CDC catch-up: complete to required watermark
Search freshness SLO: recovered
Business owner signoff: pending/approved
~~~

Các con số chỉ minh họa; unresolved cases phải có disposition/owner. Đừng báo “recovery 100% thành công” khi còn 20 conflicts chưa xử lý.

### Verification nên gồm

1. IDs và values/hashes.
2. Monotonic versions và no overwritten current records.
3. Correct tenant/owner.
4. Relationship/invariant checks.
5. SLO/read/write behavior.
6. CDC/search/cache correctness.
7. Downstream ledger và external side effects.
8. Security/audit và privacy constraints.

## 55. RPO/RTO trong recovery có chọn lọc

Giả sử:

~~~text
10:05  Bad delete
10:20  Detected
10:45  Isolated restore ready
11:00  Manifest approved
11:20  Conditional merge completed
11:40  Reconciliation completed
~~~

Nếu RTO được đo từ lúc phát hiện đến lúc các chức năng và dữ liệu cần thiết đủ dùng, thời gian là **80 phút** từ 10:20 tới 11:40. Nếu tính từ lúc lỗi bắt đầu, thời gian ảnh hưởng khác.

### Đừng chỉ đếm restore-job duration

Provider báo “restore job completed” lúc 10:45, nhưng ứng dụng chưa được khôi phục cho tới 11:40. RTO end-to-end phải tính cả scope identification, approvals, merge, validation, cutover và reconciliation theo yêu cầu nghiệp vụ.

## 56. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách tránh |
| --- | --- | --- |
| Restore đè production | Mất writes hợp lệ mới | Isolated restore + merge |
| Lấy snapshot quá cũ | Thiếu records mới | PITR và CDC replay |
| Chỉ kiểm record count | Bỏ sót trùng/mất từng ID | Set/ledger reconciliation |
| Copy cả document cũ | Reset fields mới hợp lệ | Field-level conditional patch |
| Blind upsert | Ghi đè bản current | Unique insert/CAS |
| Tin absence là accidental delete | Hồi sinh xóa hợp lệ | Audit/provenance |
| Dùng client timestamp để phân thắng thua | Sai ordering do skew | Version/commit sequence |
| Viết lại old version | Downstream bỏ event/corrupt order | Compensating new version |
| Không xử lý CDC | Search/cache stale | Rebuild/replay/watermark |
| Re-send business side effect | Double charge/award/email | Stable business identity |
| Chạy restore ở môi trường production trực tiếp | Triggers/workers hoạt động ngoài ý muốn | Isolation/gating |
| Không kiểm TTL/retention | Hồi sinh dữ liệu phải xóa | Privacy/expiry policy |
| CQL/SSTable restore không hiểu tombstone | Data resurrection/suppression | Engine-specific recovery plan |
| Coi cache là source | Phục hồi dữ liệu stale | Authority-first |
| Không có dry-run/approval | Phạm vi ghi quá rộng | Manifest + review + canary |
| Đổi backup settings trong hoảng loạn | Mất recovery points | Preserve evidence safely |
| Retry không idempotent | Nhiều restoration effects | Restoration ID/CAS |

## 57. Thiết kế phòng ngừa xóa nhầm

Khôi phục tốt vẫn đắt. Có thể giảm rủi ro bằng:

- Least-privilege service roles: job chỉ xóa trong scope cần.
- Tách `deleteMany`/`truncate`/`drop` khỏi account bình thường.
- Deletion approval cho tác vụ rộng.
- Dry-run count/sampling trước mass delete.
- Feature flag và rate limiting cho cleanup jobs.
- Soft delete/tombstone retention phù hợp.
- Backups/PITR có restore drills.
- Audited change scripts và peer review.
- Idempotency/version protocol cho mutations.
- Alert khi delete rate tăng đột ngột.
- Delete protection và control-plane policies.

Không phải dữ liệu nào cũng nên soft-delete vĩnh viễn: privacy requirements/retention cần đặt giới hạn xóa có chủ đích.

## 58. Soft delete: lợi ích và cái giá

Một document:

~~~json
{
  "id": "R101",
  "status": "CONFIRMED",
  "deletedAt": null,
  "version": 7
}
~~~

Khi xóa:

~~~json
{
  "id": "R101",
  "status": "CONFIRMED",
  "deletedAt": "2026-11-14T03:05:00Z",
  "deleteOperationId": "cleanup-42",
  "version": 8
}
~~~

Ưu điểm: có bằng chứng và có thể conditional undelete. Nhưng:

- Mọi query phải xử lý `deletedAt` đúng.
- Unique constraints/indexes có thể cần thiết kế lại.
- TTL/compaction/cost tăng.
- Không phù hợp để giữ lâu dữ liệu có yêu cầu xóa thật.
- Phải phân biệt xóa hợp lệ với xóa nhầm.

**Soft delete giúp phục hồi nhưng không phải cơ chế backup, audit hay privacy compliance thay thế.**

## 59. Guardrails cho batch cleanup

Một job xóa nên có quy trình:

~~~text
SELECT candidates (read-only)
    |
    v
Count + sample + tenant/date boundaries
    |
    v
Review threshold and approval
    |
    v
Write immutable deletion manifest
    |
    v
Delete in bounded, idempotent batches
    |
    v
Audit each batch and post-delete counts
~~~

### Ví dụ điều kiện bảo vệ

Nếu job thường xóa 100–1.000 keys/ngày mà hôm nay dự kiến 50 triệu, **tự dừng hoặc yêu cầu approval**, không coi số lượng lớn là bằng chứng job cần chạy nhanh hơn.

Không chỉ dựa vào dry-run cách đó nhiều giờ nếu dữ liệu thay đổi nhanh; apply có thể cần expected-version conditions.

## 60. Alert phù hợp để phát hiện sớm

| Metric/sự kiện | Dùng để phát hiện |
| --- | --- |
| Delete operations per minute | Tốc độ xóa bất thường |
| Delete count/estimated candidate count | Cleanup vượt dự kiến |
| High-risk admin commands | Drop/truncate/index deletion |
| Backup/PITR coverage | Mất recovery window |
| Oldest CDC position age | Recovery/replay log sắp hết hạn |
| Unexpected zero-result queries | Lỗi đọc/xóa nhầm |
| Inventory/booking invariant mismatch | Business harm |
| Search source-vs-index count/version drift | Projection lỗi |
| New restore versions applied | Tiến độ recovery |
| Conflict rate/rejected CAS | Restore gặp concurrent writes |

Đừng page chỉ vì TTL expiration bình thường. Alerts nên theo **rủi ro và phạm vi**, có owner/runbook, sample thresholds và phân biệt planned changes.

## 61. Diễn tập phục hồi phải dùng dữ liệu đại diện

Một drill có thể:

1. Tạo dataset giả chứa nhiều tenants và versions.
2. Chụp backup/PITR.
3. Thực hiện các user writes hợp lệ.
4. Xóa nhầm một subset bằng test job.
5. Tiếp tục cập nhật và xóa hợp lệ các records khác.
6. Restore về môi trường cô lập.
7. Lập dry-run manifest.
8. Chạy conditional merge và sinh conflicts có chủ đích.
9. Reconcile CDC/search/ledger.
10. Đo RTO và kiểm từng invariant.

### Điều cần chứng minh

- Affected data được cứu.
- Dữ liệu không bị xóa nhầm giữ nguyên.
- Concurrent writes không bị overwrite.
- TTL/privacy deletes không hồi sinh.
- Retry recovery không nhân đôi effects.
- Projections bắt kịp source.

Một drill chỉ restore backup thành công rồi đọc một record **chưa đủ** kiểm tính an toàn của selective recovery.

## 62. Fault matrix cho recovery

| ID | Fault | Kỳ vọng |
| --- | --- | --- |
| F1 | PITR point ngoài retention | Dừng và báo gap, không tự đoán |
| F2 | Snapshot restore thiếu index/roles | Phát hiện trước apply |
| F3 | User tạo lại record trong lúc dry-run | CAS/unique condition tránh overwrite |
| F4 | User update sau plan approval | Conflict, không blind retry |
| F5 | CDC delete event đến sau snapshot | Reconcile ordering/version |
| F6 | Recovery worker crash giữa batch | Restart idempotent |
| F7 | Duplicate restoration request | Stable restorationId ngăn double effect |
| F8 | Search consumer bị pause | Backlog alert, catch-up |
| F9 | KMS key/secret unavailable | Fail closed và có runbook |
| F10 | Bản ghi cần xóa theo privacy law | Skip/redact, không resurrect |
| F11 | Business ledger đã payment captured | Không tạo payment mới |
| F12 | Old schema backup | Migrate và validate |
| F13 | Cassandra tombstone thắng old cells | Engine-aware restore không overwrite bằng timestamp tùy tiện |
| F14 | Redis restore với `REPLACE` | Không overwrite existing keys |
| F15 | Throttling khi apply | Bounded backoff/monitor SLO |
| F16 | Recovery target kích hoạt webhook | Environment isolation/gating |

## 63. Bài tập thực hành

### Bài 1 — Restore toàn bộ

Snapshot lúc 09:55, xóa nhầm lúc 10:05, user tạo booking mới lúc 10:12. Điều gì xảy ra nếu restore production trực tiếp về 09:55?

**Gợi ý:** các writes hợp lệ sau snapshot có thể bị mất.

### Bài 2 — Xác định authority

Search index mất 1 triệu documents nhưng MongoDB authority còn đủ. Có cần restore MongoDB không? Vẽ pipeline rebuild.

### Bài 3 — Timeline

Một delete job chạy từ 10:05 đến 10:08, good writes xen giữa. Vì sao chọn PITR “10:05” chưa đủ để phân biệt good/bad operations?

### Bài 4 — Containment

Phát hiện cleanup job sai đang chạy, nhưng Booking API vẫn phục vụ khách. Nêu cách giới hạn tác hại mà không freeze toàn bộ writes.

### Bài 5 — Evidence

PITR retention 24 giờ còn CDC retention 12 giờ. Những nguồn nào cần bảo vệ ngay và vì sao?

### Bài 6 — Recovery point

Deletion bắt đầu 10:05:00, nhưng một good write commit 10:04:59 và đồng hồ application lệch 3 giây. Chọn evidence nào để định mốc PITR?

### Bài 7 — Decision matrix

Recovery copy có R101 version 7; current production có R101 version 9 do user recreate. Nên overwrite hay skip? Giải thích.

### Bài 8 — Tombstone

R101 v8 là accidental-delete tombstone, recovery có v7. Hãy mô tả restoration event và new version phù hợp.

**Gợi ý:** compensating state v9, không quay về v7.

### Bài 9 — CAS race

Recovery đọc current v8; user ghi v9 trước recovery. Điều gì xảy ra nếu unconditional put? Viết expected-version condition.

### Bài 10 — Hard-delete

Current key vắng nhưng không có audit delete reason. Vì sao insert-if-absent chưa đủ để chứng minh nên hồi sinh record?

### Bài 11 — Legitimate deletion

User đã chủ đích hủy booking sau lúc xóa nhầm. Recovery copy lại có booking cũ. Làm sao tránh hồi sinh?

### Bài 12 — Field-level patch

Backup phone=123, address=A; current phone=456, address missing do lỗi. Làm sao phục hồi A mà không ghi đè 456?

### Bài 13 — Schema migration

Backup có `totalPrice`, production dùng `amountMinor`/`currency`. Hãy đề xuất conversion và validation tests.

### Bài 14 — Dry-run

Một manifest có 50.000 records, 47.200 safe candidates, 1.900 current updated, 500 legitimate delete, 400 unknown. Hãy đề xuất cách phân batch và approvals.

### Bài 15 — Java demo

Chạy `SelectiveRecoveryDemo.java`. Vì sao A được restore nhưng B/C được giữ nguyên? Mô hình thiếu guarantee concurrency nào?

### Bài 16 — MongoDB

Viết filter với `_id`, `version`, `deleted`, `deleteOperationId` để conditional update. Khi matchedCount=0 nên làm gì?

### Bài 17 — MongoDB hard-delete

Vì sao `replaceOne` chỉ theo `_id` có thể nguy hiểm? Unique insert giúp gì, còn thiếu điều kiện nào?

### Bài 18 — Cassandra

Giải thích tại sao đưa old SSTable vào node có tombstone mới hơn không phải phương án restore đáng tin. Nêu role của timestamps/repair.

### Bài 19 — Cassandra LWT

Một conditional update `IF version=8` thất bại. Có nên dùng unconditional UPDATE ngay không?

### Bài 20 — DynamoDB

PITR tạo recovery table riêng. Thiết kế pipeline read candidates + conditional PutItem vào production và xử lý ConditionalCheckFailed.

### Bài 21 — DynamoDB unknown outcome

`PutItem` timeout sau khi server có thể đã commit. Worker retry thế nào để không tạo duplicate effect hoặc overwrite?

### Bài 22 — Redis

Redis bị xóa cache keys nhưng authoritative DB còn đúng. Khi nào chỉ cần rebuild cache? Vì sao không chạy restore snapshot với `REPLACE`?

### Bài 23 — TTL

Backup chứa voucher hết hạn lúc 10:10, hiện tại 11:00. Có nên restore với TTL mới một ngày không?

### Bài 24 — CDC

Snapshot W0, CDC events sau W0 gồm một bad delete xen good writes. Thiết kế replay có phân loại mà không bỏ lỡ updates đúng.

### Bài 25 — Ordering

Events v7, v8, v9 đến out-of-order. Làm sao tránh event v7 ghi đè state v9?

### Bài 26 — Downstream side effects

Booking restore bị consumer diễn giải thành BookingCreated rồi cộng loyalty points lần hai. Nêu protocol sửa.

### Bài 27 — Inventory

Khôi phục booking đã thanh toán nhưng inventory ledger không thay đổi. Cần kiểm những invariants gì trước khi mở API?

### Bài 28 — Multi-tenant

Hai tenants cùng có display reservationId=R101. Manifest cần chứa key nào để tránh phục hồi nhầm tenant?

### Bài 29 — Privacy

Một user đã thực hiện legitimate deletion theo retention/privacy policy, bản ghi vẫn có trong backup. Vì sao recovery phải skip?

### Bài 30 — RTO

Phát hiện lúc 10:20; restore hoàn thành 10:45; merge xong 11:20; reconciliation xong 11:40. RTO từ detection tới full recovery là bao nhiêu?

**Gợi ý:** 80 phút theo định nghĩa ví dụ.

### Bài 31 — Fault injection

Mô phỏng hai workers recovery cùng apply một record. Thiết kế condition/unique key để không nhân đôi restoration effects.

### Bài 32 — Compensating event

So sánh “ghi lại document v7” và “phát BookingRestored v9”. Phương án nào giúp audit/CDC hiểu đúng hơn?

### Bài 33 — Backup/restore drill

Thiết kế drill có snapshot, good writes sau snapshot, bad delete, user recreation, valid deletion, restore và reconcile.

### Bài 34 — Runbook

Viết runbook 10 bước từ containment, evidence, PITR isolation, dry-run đến CAS merge và business signoff.

### Bài 35 — Bài toán tổng hợp

Ứng dụng cho thuê dùng MongoDB làm booking authority, Redis cache, CDC tới search, DynamoDB cho một phần state và Cassandra event history. Một job xóa nhầm 100.000 bookings:

1. Xác định ảnh hưởng bằng audit/change logs.
2. Dừng job nhưng giữ các writes hợp lệ không liên quan.
3. Bảo vệ PITR/backup/CDC retention.
4. Restore dữ liệu cần thiết vào môi trường riêng.
5. Lập manifest theo full tenant/business keys.
6. Phân loại re-created, updated, intentionally deleted và unknown.
7. Dùng conditional update/unique insert/transactions phù hợp.
8. Không gửi lại payment/email/loyalty effects.
9. Rebuild/replay cache/search/CDC với version guards.
10. Kiểm RPO/RTO, business invariants, unresolved conflicts và signoff.

**Gợi ý:** tiêu chí thành công không phải “đã chép lại 100.000 documents”, mà là **cứu đúng dữ liệu, không phá các thay đổi hợp lệ và chứng minh kết quả**.

## 64. Checklist trước khi apply phục hồi

1. Sự cố đã được phân loại là delete/corruption thật ở source chưa?
2. Có biết source of truth của từng loại dữ liệu không?
3. Đã dừng đúng writer gây lỗi mà không làm gián đoạn không cần thiết chưa?
4. Đã bảo toàn PITR, backups, CDC, audit evidence chưa?
5. Đã xác định recovery point theo commit evidence chưa?
6. Recovery copy có được tạo ở môi trường cô lập không?
7. Recovery target có khóa workers/webhooks và giới hạn quyền không?
8. Manifest có full primary key, tenant, incident ID và provenance không?
9. Có phân biệt deleted intentionally với accidentally không?
10. Có kiểm schema/index/TTL/retention/privacy constraints không?
11. Có biết current versions của candidates không?
12. Có phân loại records created/updated sau snapshot không?
13. Apply có dùng atomic CAS/unique insert thay blind overwrite không?
14. Restore có tạo new version/audit event đúng contract không?
15. Script có idempotent restoration ID không?
16. Có tránh double payment/loyalty/email/inventory effects không?
17. Có giữ nguyên legitimate writes sau recovery point không?
18. Batch apply có canary, rate limit và stop condition không?
19. Có metrics cho applied/conflict/skip/failed không?
20. Có kiểm CDC/backlog/source-to-visible freshness không?
21. Có kiểm per-tenant correctness và relationship constraints không?
22. Có đối soát identities/values, không chỉ total count không?
23. Có xử lý unresolved conflicts bằng owner cụ thể không?
24. Có business/security approval phù hợp không?
25. Có lưu RTO thực tế, lessons learned và cleanup recovery artifacts không?

## 65. Tổng kết

1. **Xóa nhầm phải được phân biệt với TTL, soft delete, replica lag và lỗi projection.** Không restore khi chưa biết source có thực sự mất dữ liệu.
2. **Restore nguyên trạng snapshot cũ vào production có thể ghi đè những writes hợp lệ mới hơn.** Cách mặc định an toàn là isolated restore, diff, approval rồi conditional merge.
3. **Affected-set manifest phải có evidence và full business keys.** Current absence không tự chứng minh nên hồi sinh record.
4. **PITR/snapshot cung cấp recovery source**, không thay thế kiểm business legitimacy hay schema conversion.
5. **Version/CAS/unique insert bảo vệ khỏi concurrent writes**; last-write-wins theo timestamp hoặc unconditional upsert có thể phá current state.
6. **Khôi phục nên được ghi như một compensating event có version và restoration ID mới**, không âm thầm quay state/version về quá khứ.
7. **NoSQL có giới hạn riêng:** MongoDB conditional document updates, Cassandra tombstones/timestamps, DynamoDB PITR/conditional writes, Redis TTL/restore semantics.
8. **CDC, search và cache cần replay/rebuild theo watermark/version**, đồng thời giữ những deletion hợp lệ sau recovery point.
9. **Business effects ngoài database phải được đối soát**: restore booking không được tự capture payment hoặc cộng loyalty điểm lần nữa.
10. **Bảo mật và privacy không được bỏ qua**; backup có thể chứa dữ liệu đã có nghĩa vụ xóa, recovery target phải cô lập và được dọn dẹp.
11. **RTO là thời gian khôi phục toàn bộ chức năng và dữ liệu cần thiết**, không chỉ duration của restore job.
12. **Recovery thành công phải có bằng chứng**: affected IDs, versions, invariant checks, unresolved conflicts, SLO/freshness và signoff.

**Nguyên tắc thực hành:** Khi bị xóa nhầm, hãy nghĩ theo trình tự **“ngăn xóa tiếp → bảo vệ chứng cứ → phục hồi bản sao cô lập → xác minh dữ liệu thật sự cần cứu → áp dụng có điều kiện → đối soát mọi thay đổi hợp lệ và tác dụng phụ”**. Mục tiêu không chỉ đưa dữ liệu cũ trở lại, mà còn **bảo toàn dữ liệu đúng đang sống**.
