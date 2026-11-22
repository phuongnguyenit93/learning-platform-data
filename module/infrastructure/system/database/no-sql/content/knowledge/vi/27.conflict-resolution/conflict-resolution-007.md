# Giữ nhiều phiên bản, báo xung đột hoặc hợp nhất theo nghiệp vụ

Một ứng dụng đặt phòng hỗ trợ cả điện thoại lẫn máy tính. Trước khi mất mạng, hai thiết bị đều đọc booking B-901: ngày nhận phòng 10/12, hai khách. Điện thoại offline đổi ngày sang 15/12; laptop offline đổi số khách lên bốn. Khi mạng trở lại, hai cập nhật đi tới các replica khác nhau. Hệ thống nên làm gì?

- **Chọn cập nhật đến sau:** dễ làm mất một ý định hợp lệ.
- **Ghép cả hai trường:** có nguy cơ tạo booking bất hợp lệ nếu ngày mới không còn phòng cho bốn người.
- **Giữ cả hai bản:** không mất thông tin ngay, nhưng phải có quy trình kết luận trạng thái.
- **Báo xung đột:** cho phép người dùng hoặc workflow quyết định, nhưng cần giao diện và API rõ ràng.

Đây là bài toán **xung đột và đồng bộ trong NoSQL**. Khi nhiều client, vùng địa lý hoặc bản sao không nhìn thấy nhau trước khi ghi, ta cần phân biệt **phiên bản nào có quan hệ nhân quả**, **phiên bản nào cạnh tranh**, và **quy tắc nghiệp vụ nào có quyền hợp nhất hoặc từ chối thay đổi**.

Bài thuộc **Database No SQL → Xung đột và đồng bộ**, tập trung vào ba chiến lược:

1. **Giữ nhiều phiên bản:** bảo tồn các giá trị hoặc revisions chưa thể phân xử, chẳng hạn siblings/multi-value register.
2. **Báo xung đột:** dùng version token, ETag, optimistic concurrency, conflict response và thao tác resolve có chủ đích.
3. **Hợp nhất theo nghiệp vụ:** dùng semantics của operation, kiểm tra bất biến và chỉ tự động merge khi an toàn.

Nội dung mở rộng tới causal ordering, vector clocks, revision DAG, LWW, CRDT, delete/tombstone, offline sync, idempotency, Java 21, NoSQL engines, đo lường và thử nghiệm lỗi.

> **Nguyên tắc quan trọng:** **Phát hiện xung đột** không giống **giải quyết xung đột**. Vector clock có thể cho biết hai thay đổi xảy ra đồng thời theo quan hệ nhân quả, nhưng không thể quyết định số dư nào đúng, phòng nào còn trống hoặc một quyền truy cập có nên được thu hồi.

> **Phạm vi:** Khái niệm siblings, MVCC, conflict-free replicated data types, conditional updates và multi-region replication không có cùng ngữ nghĩa trong mọi engine. Các sơ đồ, API và số liệu là ví dụ học tập; bảo đảm thực tế phải được xác định theo phiên bản, cấu hình và hợp đồng sản phẩm đang dùng.

## 1. Vì sao một bản ghi có thể có nhiều phiên bản cạnh tranh?

Một hệ phân tán có thể chấp nhận thay đổi từ:

- Hai thiết bị người dùng cùng chỉnh khi offline.
- Hai region có write authority riêng.
- Replica nhận updates bất đồng bộ.
- Client dùng snapshot cũ và gửi full replacement.
- Hai request cập nhật cùng item với optimistic concurrency.
- Event replay bị trùng hoặc ngoài thứ tự.
- Retry sau khi commit ACK bị mất.
- Migration đổi schema hoặc ownership khi request cũ còn đang xử lý.

Ví dụ base:

~~~~json
{
  "bookingId": "B-901",
  "revision": "r12",
  "checkIn": "2026-12-10",
  "guestCount": 2
}
~~~~

A và B đều sửa từ r12:

~~~~text
                         r12
                       /     \
                      /       \
      A: checkIn=15/12      B: guestCount=4
                 r13a       r13b
~~~~

Nếu A không hề quan sát B, và B không hề quan sát A, chúng là **concurrent** trong causal model. Chúng không tự có thứ tự “bản nào cố ý ghi đè bản nào”.

### 1.1. Xung đột không nhất thiết là lỗi của database

Một lỗi tốt có thể là:
- Update A được commit.
- Update B nhận 412 vì base revision cũ.
- Người dùng được xem những gì đã thay đổi.

Một lỗi nguy hiểm hơn:
- A và B đều nhận 200.
- B âm thầm ghi đè toàn bộ document.
- Thay đổi của A biến mất không có audit hay cảnh báo.

**Không thấy ConflictException không chứng minh không có lost update.**

### 1.2. Những loại xung đột phổ biến

| Loại | Tình huống | Rủi ro |
| --- | --- | --- |
| Write–write | Hai updates sửa cùng field | Mất một ý định |
| Field-disjoint | Hai updates sửa các field khác nhau | Merge cấu trúc được nhưng invariant có thể sai |
| Delete–update | A xóa, B offline sửa | Hồi sinh record đã xóa |
| Create–create | Hai request cùng ý định nhưng ID khác | Duplicate booking/order |
| Schema conflict | Client cũ gửi payload v1, server đã dùng v2 | Bỏ field/sai nghĩa |
| Business conflict | Hai orders khác key giữ cùng slot | Double booking |
| Event-order conflict | Projection nhận event v15 trước v14 | State bị lùi |
| Unknown commit | Request commit nhưng ACK mất, client retry | Side effect lặp |

**Một thiết kế đúng phải phân loại xung đột theo hành vi nghiệp vụ**, không chỉ theo tên exception hoặc mức độ giống nhau của JSON.

## 2. Ba câu hỏi phải trả lời độc lập

Đối với mỗi cặp phiên bản, hỏi:

1. **Quan hệ giữa chúng là gì?** Bản sau đã thấy bản trước hay chúng concurrent?
2. **Phải giữ thông tin gì?** Một winner, nhiều siblings, toàn bộ history, events hay tombstones?
3. **Ai được quyết định trạng thái cuối?** Storage rule, domain resolver, user, admin hay transaction authority?

| Trục | Cơ chế | Không giải quyết được |
| --- | --- | --- |
| Causality/order | Sequence, version, Lamport/vector clock | Ý nghĩa nghiệp vụ |
| Retention | Snapshots, siblings, revision DAG, audit log | Chọn winner hợp lệ |
| Resolution | LWW, conflict response, CRDT, domain rules | Không tự bảo vệ write race nếu thiếu atomic commit |

Một history lưu mọi version không tự là **multi-value register**. Một engine có **MVCC** không tự trả siblings cho application. Một CRDT hội tụ tốt không tự giữ invariant tài chính.

## 3. Quan hệ nhân quả: happens-before và concurrent

Nếu cập nhật B được thực hiện sau khi người viết **đã thấy** cập nhật A, ta có thể coi A xảy ra trước B theo causal relation:

\[
A\rightarrow B
\]

Ví dụ:

~~~~text
A writes r11
B reads r11
B writes r12
~~~~

Nếu B thật sự đã thấy r11, r12 có thể supersede r11 theo version protocol.

Ngược lại:

~~~~text
A reads r10 -> writes r11a
B reads r10 -> writes r11b
~~~~

Hai cập nhật không có quan hệ trước–sau được chứng minh.

### 3.1. Wall-clock timestamp không phải causal order

Client A có đồng hồ chạy nhanh hơn 15 phút; client B ở vùng khác có đồng hồ chậm. Timestamp A lớn hơn B không chứng minh A được tạo sau B hay đã quan sát B.

Ngay cả server receive time cũng chỉ cho biết thứ tự trên đường nhận của **một server**. Network có thể delay, duplicate và reorder messages.

LWW theo timestamp có thể deterministic nhưng vẫn làm mất ý định.

### 3.2. Lamport clock có giới hạn gì?

Lamport logical clock giúp bảo đảm:

\[
A\rightarrow B\Rightarrow L(A)<L(B)
\]

Nhưng chiều ngược **không đúng tổng quát**. Chỉ biết L(A)<L(B) không chứng minh A xảy ra trước B. Lamport clock có thể dùng để tạo thứ tự logic, không phát hiện chính xác mọi cặp concurrent.

### 3.3. Vector clock

Vector clock có component theo actor/replica, ví dụ:

~~~~text
V_A={phone:2,laptop:0}
V_B={phone:1,laptop:1}
~~~~

Định nghĩa:
- \(V_a\le V_b\) nếu mọi component của a ≤ component tương ứng ở b.
- \(V_a<V_b\) nếu \(V_a\le V_b\) và ít nhất một component nhỏ hơn.
- Nếu \(V_a<V_b\), a được xem là causally earlier.
- Nếu không có quan hệ theo cả hai chiều, hai vectors **concurrent**.
- Nếu bằng nhau, chúng đại diện cùng causal frontier trong mô hình đã định.

Ví dụ:

\[
(2,0)\ \|\ (1,1)
\]

Dấu \(\|\) biểu diễn concurrent.

Một vector tiếp nhận cả hai nhánh phải phản ánh việc đã thấy cả hai, ví dụ lấy max từng component rồi tạo event mới theo quy tắc của protocol.

### 3.4. Vector clock không thay business resolver

Vector clock có thể trả lời “hai updates cạnh tranh”, nhưng không biết:
- Giá sản phẩm nào được chấp nhận.
- Khách nào được giữ slot cuối.
- Ai có quyền sửa ACL.
- Giỏ hàng có nên cộng quantity hay chọn một snapshot.

Hệ thống cần quyết định theo **domain**.

### 3.5. Chi phí metadata

Nếu có rất nhiều actor:
- Vector tăng kích thước.
- Actor identities cần lifecycle.
- Replica thay đổi thành viên.
- Clients offline rất lâu.
- Cần compaction hoặc phiên bản metadata.
- Cần xác thực causal context không bị giả mạo.

Do đó không tự triển khai vector clock production chỉ với một map và kỳ vọng nó xử lý mọi membership/recovery case.

## 4. Chiến lược thứ nhất: giữ nhiều phiên bản

Một **multi-value register** có thể giữ nhiều giá trị cùng key khi chúng concurrent:

~~~~json
{
  "entityId": "DOC-901",
  "heads": [
    {
      "revisionId": "r23a",
      "parents": ["r22"],
      "actor": "device-A",
      "content": {"title": "Bản A"}
    },
    {
      "revisionId": "r23b",
      "parents": ["r22"],
      "actor": "device-B",
      "content": {"title": "Bản B"}
    }
  ]
}
~~~~

Mỗi head phản ánh một nhánh chưa được chứng minh là đã thay thế nhánh khác.

### 4.1. Sibling là gì?

**Sibling** là một phiên bản cạnh tranh của một key, thường được giữ vì quan hệ causal/context không cho phép loại bỏ an toàn theo rules đã chọn.

Ví dụ:

~~~~text
          r23a
         /    \
r22 ----       ----> r24 merged
         \    /
          r23b
~~~~

Khi một resolution r24 đã quan sát cả r23a và r23b, có thể tạo một revision mới mang thông tin rằng **cả hai nhánh đã được xử lý**.

### 4.2. Giữ siblings khác giữ lịch sử bình thường

Lịch sử tuyến tính:

~~~~text
r1 -> r2 -> r3 -> r4
~~~~

có nhiều versions để rollback/audit nhưng chỉ có **một current head**.

Lịch sử phân nhánh:

~~~~text
r1 -> r2a
   \-> r2b
~~~~

có nhiều current heads; đấy mới là conflict representation cần resolve.

### 4.3. MVCC không tự là siblings

MVCC là một cách quản lý versions cho snapshot isolation/concurrency của storage engine. Engine có thể giữ internal snapshots nhưng API vẫn chỉ expose một committed value và dùng CAS để từ chối stale writes.

Không suy “MongoDB/DynamoDB có version hoặc transaction” nghĩa chúng luôn trả **hai sibling values** khi concurrent writes.

### 4.4. Khi nào giữ nhiều phiên bản?

- Notes/documents cần bảo toàn chỉnh sửa offline.
- Profile settings có nhiều actor và chính sách merge khác nhau.
- Các nhánh cần user review hoặc audit.
- Hệ leaderless/multi-leader phải reconcile.
- Domain chưa đủ thông tin để chọn winner ngay.
- Muốn có khả năng kiểm tra lost-update incidents.

### 4.5. Đánh đổi

- Sibling count và payload có thể tăng.
- Mỗi read phải hiểu **CONFLICTED**.
- Người dùng có thể bị yêu cầu xử lý xung đột.
- Conflict backlog cần SLA/retention.
- Storage/index/write amplification tăng.
- Quyền truy cập và xóa PII phải áp cho **mọi revision**.
- Không thể giữ conflict chưa xử lý vô hạn nếu nghiệp vụ cần một authoritative value.

### 4.6. Bản đã resolve vẫn có thể gặp conflict mới

Trong lúc người dùng xem r23a/r23b, một thiết bị C viết r23c. Nếu resolution commit mà không kiểm tra **current heads**, nó có thể vô tình xóa r23c.

Resolution phải dùng **expected head revisions/compare-and-set**, hoặc protocol tương đương.

## 5. Mô hình immutable revisions và head pointers

Một thiết kế application:

~~~~text
Revision table:
  R1: entity=DOC-901, revision=r23a, parents=[r22], content=A
  R2: entity=DOC-901, revision=r23b, parents=[r22], content=B

Head pointer:
  entity=DOC-901, heads=[r23a,r23b], state=CONFLICTED
~~~~

Khi resolve:
- Ghi r24 parents=[r23a,r23b].
- Cập nhật heads=[r24] với guard expected=[r23a,r23b].
- Ghi audit/operation result.
- Ghi outbox event cho read models.

Nếu update head pointer và insert revision là hai writes rời rạc, phải xét **atomicity**. Một failure giữa hai bước có thể để lại orphan revision hoặc head không trỏ đúng. Dùng transaction/aggregate atomicity hoặc một workflow idempotent có reconciliation.

### 5.1. Snapshot, delta và event log

| Cách lưu | Ưu điểm | Chi phí/rủi ro |
| --- | --- | --- |
| Full snapshot mỗi revision | Dễ đọc/rollback | Nhiều byte |
| Delta/patch + base | Giữ chính xác ý định field change | Cần base và chuỗi delta còn đủ |
| Immutable domain events | Audit/replay, operation semantics | Ordering, schema và dedup |
| Hybrid snapshot + events | Cân bằng performance/recovery | Nhiều phần vận hành |
| Heads + conflicts queue | Truy vấn conflict nhanh | Cần consistency với revision store |

### 5.2. Revision retention

Phải biết:
- Client có thể offline bao lâu?
- CDC/event logs giữ bao lâu?
- Có dữ liệu cần legal hold không?
- Xóa thông tin cá nhân có phải xóa history/backups?
- Có thể resolve khi base revision đã GC?
- Có cần từ chối/rebase client quá cũ?

Giữ nhiều phiên bản không có nghĩa giữ **mọi nội dung cá nhân mãi mãi**.

## 6. Chiến lược thứ hai: báo xung đột

Đối với một nguồn ghi có authority, dùng **optimistic concurrency control**:

1. Client đọc giá trị và version.
2. Client sửa dựa trên version đó.
3. Server chỉ commit nếu current version vẫn bằng expected.
4. Nếu version đã thay, server trả conflict có cấu trúc.

### 6.1. HTTP ETag / If-Match

Client đọc:

~~~~http
GET /bookings/B-901
~~~~

~~~~http
HTTP/1.1 200 OK
ETag: "booking-B-901-v12"
Content-Type: application/json

{"bookingId":"B-901","checkIn":"2026-12-10","guestCount":2}
~~~~

Sau đó gửi patch:

~~~~http
PATCH /bookings/B-901
If-Match: "booking-B-901-v12"
Content-Type: application/json

{"checkIn":"2026-12-15"}
~~~~

Nếu server thấy v13, không được tự ghi đè.

### 6.2. Các mã phản hồi

- **412 Precondition Failed:** header If-Match không còn đúng.
- **409 Conflict:** xung đột trạng thái/nghiệp vụ được API định nghĩa.
- **428 Precondition Required:** endpoint yêu cầu conditional write nhưng request không mang điều kiện.
- **400/422:** validation của nội dung không đạt, không phải đơn thuần stale version.

Một hệ có thể định nghĩa mã khác trong nội bộ; điều cần thiết là **hợp đồng API nhất quán**, cho phép client biết nên reload, resolve hay dừng.

### 6.3. Response conflict

~~~~json
{
  "status": "CONFLICT",
  "entityId": "B-901",
  "expectedRevision": "v12",
  "currentRevision": "v13",
  "conflictingFields": ["guestCount"],
  "resolutionOptions": [
    "RELOAD",
    "SAFE_MERGE",
    "MANUAL_REVIEW"
  ]
}
~~~~

Nếu trả current data, phải kiểm tra authorization/tenant scope; không để conflict response lộ nội dung của user khác.

### 6.4. Vì sao không GET phiên bản mới rồi PATCH lại mù quáng?

Nếu client đổi ngày và một actor khác đổi phòng:
- Client có thể không chấp nhận giá/phòng mới.
- Date range có thể invalid.
- Gửi lại nguyên PATCH khiến server áp một ý định lên **context chưa được người dùng đồng ý**.

Có thể retry sau reread chỉ khi:
- Domain rule cho phép.
- Recompute intent trên state mới.
- Validate lại invariant.
- Giới hạn attempts/deadline.
- Commit bằng expected version mới.

### 6.5. Conflict UI nên làm gì?

Người dùng cần thấy:
- Bản gốc đã đọc.
- Nội dung họ vừa sửa, không bị mất.
- Bản mới nhất và những thay đổi từ người/thiết bị khác.
- Các field có thể merge an toàn.
- Những field phải quyết định lại.
- Tình trạng lưu: **CHƯA LƯU / ĐANG CHỜ / ĐÃ LƯU**.

Tránh hiển thị chung chung “Save failed” rồi xóa local input.

## 7. Three-way merge: base, local, remote

Để merge đúng, cần ba phiên bản:
- **Base:** trạng thái chung mà cả hai tác nhân đã đọc.
- **Local:** thay đổi của client đang đồng bộ.
- **Remote:** trạng thái mới ở source/nhánh kia.

Ví dụ:

~~~~json
{
  "base": {"name":"An","phone":"111"},
  "local": {"name":"Bình","phone":"111"},
  "remote": {"name":"An","phone":"222"}
}
~~~~

Nếu hai field độc lập, kết quả có thể là:

~~~~json
{"name":"Bình","phone":"222"}
~~~~

### 7.1. Ma trận theo field

| Local so base | Remote so base | Hướng sơ bộ |
| --- | --- | --- |
| Không đổi | Không đổi | Giữ base |
| Thay đổi | Không đổi | Chọn local |
| Không đổi | Thay đổi | Chọn remote |
| Cùng thay đổi ra giá trị giống nhau | Cùng thay đổi | Chọn giá trị chung nếu semantics cho phép |
| Cùng thay đổi ra giá trị khác nhau | Cùng thay đổi | Báo conflict/domain rule |
| Delete | Update concurrent | Delete/update policy riêng |

### 7.2. Hai field khác nhau vẫn có thể mâu thuẫn

~~~~text
Base:   room=R1, guestCount=2
Local:  room=R2, guestCount=2
Remote: room=R1, guestCount=4
~~~~

Ghép:

~~~~text
room=R2, guestCount=4
~~~~

có thể sai nếu R2 chứa tối đa hai người. Vì vậy structural merge chỉ là **bước đề xuất**, sau đó phải **validate invariant**.

### 7.3. Full PUT làm mất ý định

Client gửi snapshot đầy đủ khi chỉ muốn đổi phone:

~~~~json
{"name":"An","phone":"222","address":"old-address"}
~~~~

Nếu server đã đổi address ở nơi khác, PUT đầy đủ có thể overwrite address mới. Một **PATCH mang rõ field intent** giúp hạn chế lỗi, nhưng vẫn cần CAS/domain validation.

### 7.4. Missing, null và remove

Ba hành vi phải tách:

~~~~text
ABSENT     -> không chỉnh field
SET_NULL   -> đặt field thành null
REMOVE     -> xóa field
~~~~

DTO với Java String field null không tự phân biệt ba ý nghĩa. Có thể cần field presence flag, typed patch operations hoặc JSON Patch được định nghĩa rõ.

## 8. Chiến lược thứ ba: hợp nhất theo nghiệp vụ

**Domain-aware merge** dùng ý nghĩa của thao tác và bất biến nghiệp vụ để tạo kết quả mới.

| Domain | Quy tắc có thể phù hợp | Điều không nên làm |
| --- | --- | --- |
| Profile preferences | Merge field độc lập | Bỏ qua validation |
| Tag add-only | Union | Dùng union khi có remove |
| Shopping cart | Merge item operations có opId | Cộng hoặc max snapshots mù |
| Note/document | 3-way/text merge, manual | LWW toàn nội dung không cảnh báo |
| View counter | Event dedup/CRDT counter | Retry increment không có ID |
| Room booking | Authority/conditional slot reserve | Confirm cả hai concurrent intents |
| Inventory | Conditional decrement/escrow rights | Merge hai stock snapshots |
| Wallet/balance | Authoritative ledger | LWW hoặc cộng balances |
| Access control | Revocation semantics/authority | Union permissions vô điều kiện |
| Product price | Approval/authority | Lấy max/min mà không business reason |

### 8.1. Không phải mọi trường đều có thể hợp nhất

Một object có thể merge field description tự động, nhưng:
- Price cần approval.
- Availability cần authority.
- Permission cần security policy.
- Currency/amount cần numeric precision và transaction contract.

Hãy định nghĩa **policy ở cấp field hoặc domain command**, không nhất thiết một merge strategy cho cả document.

### 8.2. Validate sau merge và commit có điều kiện

Luồng:

~~~~text
Collect versions
  -> detect concurrent updates
  -> apply safe merge policy
  -> validate schema
  -> validate business invariants
  -> CAS / transaction commit against current heads
  -> write operation result + outbox
~~~~

Nếu current heads thay đổi trong lúc validate, CAS phải thất bại và quy trình cần reread/recompute hoặc báo conflict.

### 8.3. Operation semantics thường quan trọng hơn final snapshot

Ví dụ quantity:
- “Bấm +1” là **delta operation**.
- “Đặt quantity bằng 2” là **assignment**.
- “Xóa SKU” là **remove**.

Ba operation không thể xử lý bằng một phép max/sum chung.

### 8.4. Quy tắc quyết định

Một mặc định thận trọng:
- Tự merge những thay đổi có thể chứng minh an toàn.
- Giữ đủ causal/intent information.
- Báo người dùng khi có nhiều lựa chọn hợp lệ cần phê duyệt.
- Reject khi invariant bị phá.
- Không âm thầm thay đổi cam kết tài chính, booking hay quyền truy cập.

## 9. Last-write-wins (LWW) và mất cập nhật im lặng

LWW thường chọn giá trị dựa trên timestamp/ordering rule.

Nó có thể phù hợp với:
- Presence.
- Cache state có thể tái tính.
- Telemetry với semantics “latest measurement”.
- Một field được chính sách cho phép overwrite.

Không nên mặc định với:
- Số dư.
- Booking.
- Inventory.
- ACL.
- Tài liệu người dùng quan trọng.

### 9.1. Clock skew

~~~~text
A đồng hồ nhanh 10 phút: status=OFFLINE
B thực tế sửa sau:       status=ONLINE
~~~~

Nếu A có timestamp lớn hơn, LWW có thể giữ OFFLINE dù B là thao tác sau theo thời gian thực.

### 9.2. Server timestamp cũng không chắc phản ánh ý định

Một update có thể bị delayed trên network trước khi tới server. Hai region nhận khác thứ tự. Thời điểm arrival không chứng minh client đã thấy revision trước.

### 9.3. Deterministic nhưng không đúng nghiệp vụ

Một tie-breaker như (timestamp,actorId) có thể khiến mọi replica chọn cùng winner, tốt cho convergence. Tuy nhiên vẫn có thể xóa một chỉnh sửa hợp lệ.

**Deterministic convergence không đồng nghĩa domain correctness.**

### 9.4. Muốn LWW phải công bố giới hạn

Cần ghi rõ:
- Timestamp lấy từ đâu.
- Clock assumptions.
- Tie-breaker.
- Có lưu loser/audit không.
- Delete/tombstone policy.
- Các field nào được cho phép mất intermediate changes.
- Cách sửa sai khi timestamp bất thường.

## 10. CRDT và tự hội tụ

**Conflict-free replicated data types (CRDTs)** có những quy tắc state hoặc operation được thiết kế để hội tụ khi message trễ, duplicate hoặc đến không cùng thứ tự, trong các giả định phù hợp.

### 10.1. Phép merge state-based thường cần

- **Commutative:** merge(a,b)=merge(b,a).
- **Associative:** merge(merge(a,b),c)=merge(a,merge(b,c)).
- **Idempotent:** merge(a,a)=a.

Những tính chất này giúp không phụ thuộc thứ tự truyền state.

### 10.2. G-Counter

Mỗi replica giữ một thành phần đếm tăng đơn điệu:

~~~~text
State A={A:5,B:1}
State B={A:4,B:3}
Merge=max(component-wise)={A:5,B:3}
Value=5+3=8
~~~~

Merge lại cùng state không tăng đếm thêm. Nhưng một G-Counter không xử lý decrement tự nhiên.

### 10.3. PN-Counter

PN-Counter lưu:
- P: increments.
- N: decrements.
- Value=P−N.

Nó có thể hội tụ, nhưng **không bảo đảm tồn kho không âm** khi nhiều vùng decrement độc lập. Muốn bounded inventory cần escrow rights hoặc authority mạnh.

### 10.4. Set merge: add-wins, remove-wins

Hai replicas đồng thời:
- A thêm tag VIP.
- B xóa tag VIP.

Có thể định nghĩa:
- Add-wins.
- Remove-wins.
- Observed-remove, chỉ xóa adds đã thấy.

Không có lựa chọn đúng cho mọi domain:
- User interests có thể add-wins.
- Permission revocation có thể cần remove-wins hoặc authority/security rule nghiêm ngặt.

### 10.5. CRDT khác idempotent event processing

State merge idempotent không có nghĩa một event “debit 100” có thể apply hai lần. Operation-based CRDT và event stream có delivery/causal assumptions riêng. Cần operationId/eventId và xử lý đúng semantics.

### 10.6. Metadata và garbage collection

OR-Set, sequence CRDT và multi-value register có thể giữ dots/tags, vector clocks, tombstones. Khi nhiều actor, kích thước metadata tăng; cần retention/compaction theo giả định replica/offline duration.

**CRDT không phải phương pháp bỏ hết transaction, authorization và business constraints.**

## 11. Giỏ hàng: merge snapshots không giống merge operations

Giả sử base quantity của SKU-9 = 1:
- Điện thoại offline bấm +1 → local snapshot quantity=2.
- Laptop offline bấm +1 → remote snapshot quantity=2.

Nếu lấy max:

\[
\max(2,2)=2
\]

một ý định bị mất.

Nếu cộng hai snapshots:

\[
2+2=4
\]

base bị tính hai lần.

Nếu lưu deltas riêng có IDs:

~~~~json
{
  "baseQuantity": 1,
  "operations": [
    {"operationId":"INC-A","delta":1},
    {"operationId":"INC-B","delta":1}
  ]
}
~~~~

thì kết quả khi dedup đúng:

\[
1+1+1=3
\]

### 11.1. Nhưng remove và increment concurrent thì sao?

Ví dụ:
- A bấm REMOVE SKU.
- B bấm +1.

Ứng dụng phải chọn policy:
- Remove-wins.
- Add-wins.
- Giữ conflict để xác nhận.
- Một “reset generation” để các increments cũ không hồi sinh SKU.

Không phải phép cộng nào cũng xử lý đúng remove.

### 11.2. Checkout là ranh giới khác

Cart có thể hội tụ eventual; nhưng khi checkout:
- Giá/tồn kho có thể đổi.
- Khuyến mãi hết hạn.
- Stock có giới hạn.
- Tax/shipping phải tính lại.

**Cart merge là hợp nhất ý định; checkout phải xác nhận điều kiện nghiệp vụ ở source có thẩm quyền.**

## 12. Booking: không thể merge hai xác nhận cùng slot

Một phòng R-08 chỉ còn một slot:
- Vùng VN tạo intent A.
- Vùng EU tạo intent B.

Set union:

~~~~text
Bookings={A,B}
~~~~

có thể hội tụ, nhưng business bị **double booking** nếu cả A và B đều CONFIRMED.

### 12.1. Một authority hoặc quyền phân bổ

Một thiết kế dùng:

~~~~text
SlotKey = TENANT#T42#ROOM#R08#DAY#2026-12-15
~~~~

với atomic conditional guard:

~~~~text
IF slot.status == FREE:
    slot.status=RESERVED
    slot.bookingId=B-901
ELSE:
    reject_or_waitlist
~~~~

Hai concurrent requests được phân xử tại một điểm có authority.

### 12.2. Giữ intents khác xác nhận kết quả

Có thể lưu cả A và B thành:
- Intent A.
- Intent B.
- Một winner CONFIRMED.
- Một loser WAITLISTED/REJECTED.

Đừng cho người dùng thấy cả hai booking confirmed chỉ vì hệ chấp nhận ghi local.

### 12.3. Escrow rights có phạm vi riêng

Khi tài nguyên có thể chia đơn vị (quota 100):
- Vùng VN có quyền chi 60.
- EU có 40.
- Mỗi vùng không được vượt budget.
- Chuyển quyền phải bảo toàn tổng và chống double spending.

Nhưng **một slot duy nhất** không dễ tách thành nhiều quyền độc lập mà không phá invariant.

## 13. Số dư, thanh toán và ledger

Số dư 100:
- A offline debit 70 → snapshot balance=30.
- B offline debit 60 → snapshot balance=40.

LWW 30 hoặc 40 làm mất một debit. Cộng snapshots 30+40=70 cũng sai. Cộng delta 100−70−60=−30 phát hiện vượt hạn nhưng nếu cả hai debit đã được xác nhận thì đã có vấn đề business.

Cần:
- Authoritative ledger.
- TransactionId/operationId chống duplicate.
- Conditional reserve hoặc protocol phân quyền thích hợp.
- Quy trình reconcile/reversal.
- Không confirm debit khi authority không đủ điều kiện.
- Audit những lần retry/timeout.

**Một phép merge hội tụ tốt không tự chứng minh “balance never negative”.**

## 14. Security: conflict giữa grant và revoke

Hai thay đổi đồng thời:
- Admin A revoke quyền WRITE.
- Offline client B grant WRITE.

Union permissions có thể cấp lại quyền đã thu hồi. Cần:
- Quy tắc revocation rõ.
- Authority/epoch hoặc version của policy.
- Authorization khi áp offline operation.
- Kiểm soát caches/tokens.
- Audit.
- Fail-closed ở endpoint nhạy cảm.

**Permission set không phải add-only tag set.** Không dùng một merge rule cho cả sở thích và quyền truy cập.

## 15. Delete–update: tombstone và resurrection

Giả sử A xóa DOC-901, nhưng B offline vẫn có r12 rồi cập nhật text. Khi B sync:
- Nếu server không nhớ delete, update cũ có thể tạo lại document.
- Nếu LWW tùy clock, delete có thể thua sai.
- Nếu giữ siblings, cần giữ cả tombstone và update cạnh tranh cho resolver.

Một tombstone:

~~~~json
{
  "entityId": "DOC-901",
  "revisionId": "r13-delete",
  "deleted": true,
  "causalContext": {"A":5,"B":2},
  "deletedAt": "2026-11-14T09:00:00Z"
}
~~~~

### 15.1. Delete-wins / update-wins / manual

- **Delete-wins:** phù hợp một số chính sách xóa/tính riêng tư.
- **Update-wins:** có thể phù hợp tài liệu cộng tác nếu xóa chỉ là thao tác tạm.
- **Keep both:** giữ tombstone và revision update để người dùng quyết định.
- **Soft-delete/restore:** cho khôi phục có chủ đích, ghi audit.

### 15.2. Tombstone retention

Nếu tombstone bị GC sau 7 ngày nhưng thiết bị offline 30 ngày:
- Thiết bị có thể gửi update cũ.
- Không còn delete marker đủ ngăn resurrection.
- Read models có thể tái tạo record đã xóa.

Phải xét:
- Offline window.
- Max replica outage.
- Log/CDC retention.
- Repair/anti-entropy.
- Snapshot/backup restore.
- Legal retention/erasure requirements.

### 15.3. Xóa dữ liệu cá nhân

Giữ mọi revision vô hạn có thể mâu thuẫn với chính sách xóa dữ liệu. Phải thiết kế:
- Data deletion trên source/history/index/cache/backup theo khả năng.
- Metadata audit tối thiểu.
- Legal hold exceptions.
- Retention giới hạn.
- Quyền truy cập vào historical siblings.

**Không dùng “giữ nhiều version” như lý do bỏ qua erasure policy.**

## 16. Event sourcing và giữ ý định

Thay vì overwrite trạng thái cuối, có thể giữ commands/events:

~~~~text
BookingCreated(B-901)
GuestCountChanged(B-901,2->4)
CheckInChanged(B-901,10->15)
BookingConfirmed(B-901)
~~~~

Mỗi event mang:
- eventId.
- operationId.
- aggregateId.
- expectedAggregateVersion hoặc causal context.
- schemaVersion.
- actor/provenance có quyền.
- business intent.

### 16.1. Ưu điểm

- Audit.
- Rebuild read models.
- Hiểu ý định thay vì chỉ snapshot.
- Phát hiện duplicate/out-of-order.
- Đối soát sau failover.

### 16.2. Không phải mọi event đều tự commutative

Hai events:
- SetPrice(100).
- SetPrice(200).

không có phép “cộng” hợp lý. Một event log có thứ tự authoritative có thể chọn thứ tự commit; nếu hai regions có logs độc lập, vẫn phải reconcile.

### 16.3. Event delivery có thể trùng

Producer retry sau mất ACK:
- Event được publish hai lần.
- Consumer phải dedup theo eventId.
- Projection cần lastAppliedVersion hoặc idempotent update.
- Không tự suy exactly-once end-to-end chỉ vì dùng outbox.

## 17. Outbox/CDC và read models

Một pipeline:

~~~~mermaid
flowchart LR
    API["Command + conflict decision"] --> AUTH[("Authoritative NoSQL")]
    AUTH --> OUT[("Outbox / changelog")]
    OUT --> BUS["CDC / event bus"]
    BUS --> SEARCH[("Search projection")]
    BUS --> ANALYTICS[("Analytics")]
    BUS --> AUDIT[("Revision audit")]
~~~~

### 17.1. Conflict resolution phải commit tại authority

Hướng hợp lý:
1. Nhận command với expected version.
2. Detect stale/concurrent change.
3. Keep candidate hoặc apply domain resolver.
4. Validate.
5. Conditional commit.
6. Ghi outbox.
7. Projectors cập nhật sau.

Nếu publish BookingConfirmed từ một sibling chưa qua authority, các hệ downstream có thể hành động trên một ý định **chưa hợp lệ**.

### 17.2. Index visibility khác source commit

Source đã commit r24 nhưng search vẫn ở r23. Search không thấy r24 chưa chứng minh resolution thất bại. Cần freshness SLO và đường kiểm tra source phù hợp.

### 17.3. Reorder v15 trước v14

Một consumer có thể nhận:
- Version 15.
- Version 14 đến muộn.

Nếu apply arrival-order, state đi lùi. Dùng aggregateVersion/eventId và xử lý gaps/out-of-order theo semantics. Không bỏ event thấp hơn mù quáng nếu nó mang thông tin cần audit hoặc là delta độc lập.

## 18. Mô hình conflict record cho application

~~~~json
{
  "conflictId": "CF-901",
  "tenantId": "T-42",
  "entityType": "Booking",
  "entityId": "B-901",
  "status": "UNRESOLVED",
  "baseRevision": "r12",
  "headRevisions": ["r13a","r13b"],
  "policyVersion": "booking-merge-v3",
  "riskClass": "BUSINESS_REVALIDATION",
  "conflictingFields": ["checkIn","guestCount"],
  "resolutionOperationId": null
}
~~~~

Các trạng thái có thể:

~~~~text
DETECTED
  -> AUTO_MERGE_CANDIDATE -> VALIDATING -> RESOLVED
  -> MANUAL_REVIEW -> RESOLVED
  -> ESCALATED
  -> REOPENED if new concurrent head appears
~~~~

### 18.1. Atomic resolution

Nếu user chọn merge:
- Server xác minh expected head set.
- Validate business rules.
- Ghi revision mới parents=[r13a,r13b].
- Ghi operation ledger và outbox.
- Commit trong transaction/atomic boundary phù hợp.

Nếu một head mới xuất hiện, CAS phải từ chối để tránh xóa ý định mới.

### 18.2. Conflict queue không được tăng vô hạn

Theo dõi:
- Siblings per key.
- Max unresolved age.
- Bytes per conflict.
- Manual-review backlog.
- Reopened conflicts.
- High-risk domain conflicts.

Có thể archive/quarantine những intents quá cũ theo retention, nhưng không silent drop khi cần audit/recovery.

### 18.3. Quyền xem historical revisions

Mỗi conflict có thể chứa nội dung của nhiều actor. Endpoint phải kiểm tra:
- Tenant scope.
- Quyền đọc fields.
- Quyền resolve.
- Policy của dữ liệu đã xóa.
- PII retention.

Không để conflictId đoán được tạo cross-tenant data leak.

## 19. API sync offline

Client queue:

~~~~json
{
  "entityId": "B-901",
  "deviceId": "device-A",
  "operationId": "OP-901",
  "baseRevision": "r12",
  "schemaVersion": 2,
  "patch": {"checkIn":"2026-12-15"}
}
~~~~

Server có thể trả:

~~~~json
{
  "outcome": "CONFLICT",
  "conflictId": "CF-901",
  "baseRevision": "r12",
  "currentRevision": "r13b",
  "intentRecorded": true,
  "resolutionRequired": true
}
~~~~

**IntentRecorded không đồng nghĩa booking update đã CONFIRMED.**

### 19.1. Client cần giữ gì?

- Stable operationId qua retry/restart.
- Base revision/causal token.
- Local edit intent, không chỉ full snapshot cuối.
- Schema version.
- Trạng thái gửi/ACK/PENDING/CONFLICT.
- Tính nguyên vẹn của local queue.
- Một đường reload/rebase khi token cũ.

### 19.2. Sync theo operation vs snapshot

Snapshot:

~~~~json
{"guestCount":4,"checkIn":"2026-12-10"}
~~~~

không nói client đã sửa gì.

Operation:

~~~~json
{
  "type":"SET_GUEST_COUNT",
  "value":4,
  "baseRevision":"r12",
  "operationId":"OP-77"
}
~~~~

giúp resolver biết ý định. Nhưng có operation intent vẫn phải validate phòng, giá và quyền.

### 19.3. Offline quá lâu

Một client offline sáu tháng có thể:
- Base revision bị GC.
- Schema v1 đã hết hỗ trợ.
- Entity đã bị xóa.
- Quyền client đã bị thu hồi.
- Price/terms thay đổi.

Có thể trả STALE_BASE_REQUIRES_RELOAD và giữ local edit để user chọn. Không hứa mọi offline update đều merge được.

## 20. Read-your-writes và monotonic reads giảm xung đột giả

Một người dùng sửa ở VN rồi đọc ngay replica EU:
- EU có thể còn v12.
- Người dùng chỉnh dựa trên v12 dù source đã có v13.
- Sync trở lại sinh conflict không cần thiết.

Nếu API hỗ trợ session/causal token:
- Client mang minVersion.
- Read chờ hoặc route tới replica đủ mới.
- Không trả v12 dưới lời hứa read-your-writes.

Nếu chỉ eventual:
- UI nên công bố “last synced”.
- Tránh cho thực hiện hành động nhạy cảm dựa trên stale state.
- Lưu baseRevision để phát hiện conflict.

**Một replica có dữ liệu cũ không làm source write trước đó bị rollback.**

## 21. Java 21: kết quả cập nhật có kiểu rõ

~~~~java
import java.util.List;

public sealed interface UpdateOutcome
        permits UpdateOutcome.Committed,
                UpdateOutcome.Conflict,
                UpdateOutcome.Rejected,
                UpdateOutcome.Unknown {

    record Committed(
            String entityId,
            String newRevision
    ) implements UpdateOutcome {}

    record Conflict(
            String entityId,
            String baseRevision,
            List<String> currentHeads,
            String conflictId
    ) implements UpdateOutcome {}

    record Rejected(
            String entityId,
            String reasonCode
    ) implements UpdateOutcome {}

    record Unknown(
            String operationId,
            String explanation
    ) implements UpdateOutcome {}
}
~~~~

### 21.1. Tách Conflict khỏi UNKNOWN

- **Committed:** có bằng chứng đã commit.
- **Conflict:** expected precondition/head set không khớp.
- **Rejected:** validation/invariant không cho phép.
- **Unknown:** request có thể đã commit nhưng client không thấy kết quả.

Một timeout network sau gửi write **không phải bằng chứng REJECTED**.

### 21.2. UI xử lý

~~~~java
public String message(UpdateOutcome result) {
    return switch (result) {
        case UpdateOutcome.Committed c ->
                "Đã lưu " + c.newRevision();
        case UpdateOutcome.Conflict c ->
                "Có thay đổi đồng thời; cần chọn cách hợp nhất.";
        case UpdateOutcome.Rejected r ->
                "Không thể lưu: " + r.reasonCode();
        case UpdateOutcome.Unknown u ->
                "Chưa xác minh được kết quả thao tác.";
    };
}
~~~~

Java switch pattern matching là ví dụ cho Java 21; chưa bao gồm localization/accessibility hoặc workflow UI thực.

## 22. Java: repository và CAS

~~~~java
public interface BookingRepository {
    UpdateOutcome patch(
            String tenantId,
            String bookingId,
            long expectedVersion,
            BookingPatch patch,
            String operationId
    );

    BookingSnapshot readAuthoritatively(
            String tenantId,
            String bookingId
    );

    UpdateOutcome findOperationResult(
            String tenantId,
            String operationId
    );
}
~~~~

BookingPatch/BookingSnapshot là kiểu application định nghĩa.

### 22.1. Read rồi write không atomic là sai

~~~~text
current = read(B-901)
if current.version == 12:
    write(B-901, changedValue)
~~~~

Một request khác có thể commit v13 sau read trước write.

Cần atomic conditional operation:

~~~~text
UPDATE booking
SET value=..., version=13
WHERE id=B-901 AND version=12
~~~~

### 22.2. Một version integer chỉ phù hợp với authority có thứ tự

Nếu VN và EU độc lập cùng đọc v12 rồi tự tăng:
- VN có v13a.
- EU có v13b.

Chỉ thấy integer 13 không đủ phân biệt. Cần unique revision identities/causal context hoặc một authority áp ordering.

### 22.3. Retry CAS khi conflict

Quy trình:
1. Đọc lại authoritative current version.
2. Recompute intent theo domain.
3. Validate.
4. CAS với expected current version.
5. Giới hạn số vòng; nếu không hợp nhất được, trả conflict.

Không auto retry nguyên payload cũ với một expected version mới để “ép qua” guard.

## 23. Java: so sánh vector clocks

~~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class VectorClockOrder {
    private VectorClockOrder() {}

    public enum Relation {
        EQUAL, BEFORE, AFTER, CONCURRENT
    }

    public static Relation compare(
            Map<String, Long> a,
            Map<String, Long> b
    ) {
        Objects.requireNonNull(a);
        Objects.requireNonNull(b);

        Set<String> actors = new HashSet<>();
        actors.addAll(a.keySet());
        actors.addAll(b.keySet());

        boolean less = false;
        boolean greater = false;

        for (String actor : actors) {
            long av = a.getOrDefault(actor, 0L);
            long bv = b.getOrDefault(actor, 0L);

            if (av < 0 || bv < 0) {
                throw new IllegalArgumentException(
                        "negative vector clock counter");
            }

            if (av < bv) less = true;
            if (av > bv) greater = true;

            if (less && greater) {
                return Relation.CONCURRENT;
            }
        }

        if (!less && !greater) return Relation.EQUAL;
        return less ? Relation.BEFORE : Relation.AFTER;
    }
}
~~~~

Ví dụ:

~~~~java
var a = Map.of("phone", 2L, "laptop", 0L);
var b = Map.of("phone", 1L, "laptop", 1L);

var result = VectorClockOrder.compare(a,b);
// CONCURRENT
~~~~

**Giới hạn:**
- Không triển khai increment, merge, GC vector.
- Actor identities phải được xác thực.
- Counter cần tránh overflow/reuse.
- Nhiều actor gây metadata growth.
- Không tự giải quyết business conflict.
- Không thay replica protocol hoặc database transaction.

## 24. Java: phát hiện field conflicts

~~~~java
import java.util.Map;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Set;
import java.util.Objects;

public record FieldMerge(
        Map<String, Object> merged,
        Set<String> conflictingFields
) {}

public final class ThreeWayFields {
    private ThreeWayFields() {}

    public static FieldMerge merge(
            Map<String, Object> base,
            Map<String, Object> local,
            Map<String, Object> remote
    ) {
        Set<String> keys = new HashSet<>();
        keys.addAll(base.keySet());
        keys.addAll(local.keySet());
        keys.addAll(remote.keySet());

        Map<String, Object> merged = new HashMap<>();
        Set<String> conflicts = new HashSet<>();

        for (String key : keys) {
            Object b = base.get(key);
            Object l = local.get(key);
            Object r = remote.get(key);

            boolean lc = !Objects.equals(l, b);
            boolean rc = !Objects.equals(r, b);

            if (lc && rc && !Objects.equals(l,r)) {
                conflicts.add(key);
            } else if (lc) {
                merged.put(key,l);
            } else {
                merged.put(key,r);
            }
        }

        return new FieldMerge(
                Map.copyOf(merged),
                Set.copyOf(conflicts)
        );
    }
}
~~~~

**Cảnh báo mã mẫu:**
- Map.get không phân biệt missing và null.
- Map.copyOf không chấp nhận null values.
- Nested objects/lists cần semantics riêng.
- Không validate invariant liên field.
- Không xử lý domain commands hay side effects.
- Không commit atomically.
- Không có causal metadata.

Đây là **bộ minh họa cấu trúc**, không phải resolver dùng production trực tiếp. Trong một hệ thực, patch operations phải có presence semantics và validation.

## 25. Resolution request cần idempotency

Người dùng đã chọn hợp nhất:
- Server commit r24.
- ACK bị mất.
- Client retry.

Nếu mỗi retry tạo một resolutionOperationId mới:
- Có thể tạo revision/notification trùng.
- Có thể lặp side effect.

Request nên có:

~~~~json
{
  "resolutionOperationId": "RESOLVE-901",
  "conflictId": "CF-901",
  "expectedHeadRevisions": ["r23a","r23b"],
  "decision": "MERGE",
  "resultFingerprint": "sha256:..."
}
~~~~

Server:
1. Kiểm tra operationId đã có kết quả chưa.
2. Cùng ID + khác payload → conflict.
3. Validate expected heads vẫn hiện hành.
4. Validate schema/business.
5. Commit revision + ledger + outbox trong ranh giới atomicity phù hợp.
6. Retry cùng ID trả prior result.

**Giải quyết xung đột chính nó có thể xung đột hoặc mất ACK**. Không có bước ghi nào được miễn retry/idempotency.

## 26. Quy tắc merge phải deterministic và versioned

Nếu hai replicas tự merge cùng tập siblings A/B, mong muốn:
- Thứ tự event đến không đổi outcome.
- Replay không tạo side effect mới.
- Duplicate events không làm thay result.
- Serialization/numeric/time zone nhất quán.

Cần lưu:
- policyId.
- policyVersion.
- schemaVersion.
- revision lineage.
- decision operator/authority.
- operationId/result.

### 26.1. Random winner và system clock

Nếu resolver tự random chọn A/B ở từng replica, chúng có thể không hội tụ. Nếu phải dùng một lựa chọn nondeterministic, hãy đưa quyết định về **một authority**, ghi nó thành event/version và replay cùng kết quả.

### 26.2. Replay với policy mới

Policy v1 add-wins, policy v2 remove-wins:
- Replay cùng lịch sử có thể cho trạng thái khác.
- Migration phải có version cutover/checkpoint rõ.
- Audit phải biết quyết định từng thời điểm.
- Không âm thầm đổi policy rồi rebuild projections như thể kết quả luôn giống.

### 26.3. Tie-breaker

Một tuple (sequence,operationId) có thể deterministic theo giao thức cụ thể. Nhưng deterministic chỉ giúp hội tụ; phải chứng minh **rule đó được domain cho phép**.

## 27. Multi-leader và leaderless systems

Hai vùng chấp nhận write độc lập:

~~~~text
VN: r12 -> r13a
EU: r12 -> r13b
         |
     network heals
         v
   replication exchanges revisions
         |
   conflict resolution
~~~~

Lợi ích:
- Một số local/offline writes có latency thấp.
- Có thể nhận intents khi vùng kia không truy cập.
- Tăng khả năng ghi trong một số fault models.

Đánh đổi:
- Conflict metadata/anti-entropy.
- Domain rules.
- Uniqueness và inventory invariant xuyên vùng.
- Delete/tombstone handling.
- Replay/reconciliation.
- Người dùng có thể thấy state khác nhau theo region.

### 27.1. Auto LWW không làm xung đột biến mất về nghiệp vụ

Engine chọn winner và app chỉ thấy một value. Ý định bị thua có thể mất nếu không có history riêng. **ConflictCount=0** trên dashboard không chứng minh không có lost updates.

### 27.2. Chấp nhận intent khác confirm business outcome

Có thể nhận draft/cart updates offline, nhưng booking hoặc payment cần authority/ràng buộc rõ trước khi trả CONFIRMED.

## 28. Quorum/consensus và conflict

Một consensus-backed aggregate có thể serialize writes:
- Leader/authority chấp nhận commands.
- Commit theo protocol.
- CAS từ chối client stale.
- Không cho hai cạnh tranh cùng confirm slot.

Nhưng vẫn có:
- Optimistic conflicts.
- Client offline edits dựa trên revision cũ.
- Business validation conflicts.
- External payment side effects.
- Read replica/search lag.
- ACK unknown.

**Consensus giúp quyết định thứ tự, không thay domain quyết định command nào được chấp nhận.**

### 28.1. Không dùng eventual read để resolve bản mới nhất

Follower/search có thể trả v12 trong khi source đã v13. Resolver cần đọc authoritative/latest-enough state theo contract, không lấy một eventual query làm bằng chứng chưa có conflict.

### 28.2. Multi-shard transaction

Một nghiệp vụ ghi:
- Inventory.
- Order.
- OperationResult.
- Outbox.

Dù từng write có quorum, chúng không tự all-or-nothing. Cần transaction hoặc workflow có compensation/reconciliation rõ.

## 29. MongoDB: version field và application history

MongoDB cho phép atomic conditional update đối với document theo khả năng API, có transaction trong phạm vi được hỗ trợ. Một ứng dụng có thể dùng version.

Dữ liệu:

~~~~json
{
  "_id":"B-901",
  "tenantId":"T-42",
  "version":12,
  "guestCount":2
}
~~~~

Ví dụ Java driver:

~~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;

public final class BookingMongoVersioned {
    private final MongoCollection<Document> bookings;

    public BookingMongoVersioned(MongoCollection<Document> bookings) {
        this.bookings = bookings;
    }

    public boolean changeGuestCount(
            String tenantId,
            String bookingId,
            long expectedVersion,
            int guestCount
    ) {
        UpdateResult result = bookings.updateOne(
                and(
                        eq("_id",bookingId),
                        eq("tenantId",tenantId),
                        eq("version",expectedVersion)
                ),
                combine(
                        set("guestCount",guestCount),
                        inc("version",1L)
                )
        );
        return result.getMatchedCount() == 1L;
    }
}
~~~~

### 29.1. CAS bảo vệ gì?

Hai concurrent updates cùng expectedVersion=12: sau khi một update đổi version lên 13, update khác không còn match. Nó không được silently overwrite.

### 29.2. CAS chưa giải quyết gì?

- Business invariant ở document khác.
- Không giữ revision history nếu chỉ overwrite.
- Không lưu tất cả siblings tự động.
- Không bảo vệ external payment.
- Không giải quyết lost ACK/idempotency.

### 29.3. MatchedCount=0 có nhiều nguyên nhân

Document không tồn tại, tenant khác, bị xóa hoặc version stale. Không trả thông tin tồn tại của record khác tenant chỉ vì muốn giải thích conflict.

### 29.4. ACK mất

Nếu update v12→v13 đã commit rồi ACK mất, retry v12 có thể matchedCount=0. Cần operation ledger để xác định prior result, không tự tạo một ý định mới.

## 30. Cassandra: LWW ordinary writes và LWT

Trong Cassandra, ordinary storage writes có timestamp/tombstone/conflict semantics riêng; không tự trả all siblings như application MV-register.

- Normal QUORUM không có nghĩa mọi write nằm trong một Raft replicated log.
- LWT/conditional updates có API/serial consistency riêng.
- Client-generated timestamps cần được xử lý cẩn thận.
- Tombstones/repair/retention ảnh hưởng delete resurrection risk.

Một CAS minh họa theo schema thích hợp:

~~~~sql
UPDATE bookings
SET guest_count = 4, version = 13
WHERE tenant_id = 'T-42'
  AND booking_id = 'B-901'
IF version = 12;
~~~~

Khi condition không được applied, client cần conflict handling; khi timeout có thể UNKNOWN. Không retry cùng stale version vô hạn.

### 30.1. Không lấy collection type làm CRDT bảo đảm

Set/list/map CQL có update semantics riêng, không tự tạo add-wins/remove-wins offline convergence hay transaction bảo vệ inventory. Phải thiết kế đúng domain operation.

### 30.2. Nếu cần siblings

Lưu application revision/history và reconcile qua một authority/workflow được định nghĩa, không giả định ordinary cell overwrites giữ các phiên bản thua.

## 31. DynamoDB: ConditionExpression, transactions và global replication

Một conditional UpdateItem có thể kiểm tra expected version:

~~~~text
ConditionExpression:
    #version = :expected

UpdateExpression:
    SET #guestCount = :newCount,
        #version = :nextVersion
~~~~

Nếu condition fails, không auto retry y hệt như transient error; cần đọc lại và áp domain policy.

### 31.1. Transaction khác revision DAG

TransactWriteItems có thể bảo vệ nhiều items trong giới hạn API, nhưng không tự giữ history/siblings. Nếu cần giữ hai offline intents, application phải lưu revisions/conflict records.

### 31.2. Global tables phải xét mode

Các mode/tính năng đa vùng có consistency/replication behavior khác nhau theo cấu hình. Không tự suy mọi global-table deployment đều có:
- Global linearizable writes.
- Cross-region atomic uniqueness.
- Cùng LWW/conflict policy.
- Strong reads ở mọi region.

Cần kiểm tra authority/replication mode cụ thể.

### 31.3. GSI có thể stale

GSI được cập nhật bất đồng bộ theo contract. Không dùng “GSI chưa thấy item” để kết luận conditional source write chưa commit.

## 32. Redis: optimistic concurrency và giới hạn

Redis WATCH/MULTI/EXEC có thể dùng cho optimistic updates trong phạm vi phù hợp:

~~~~text
WATCH booking:B-901
GET booking:B-901
# read version=12, compute patch
MULTI
SET booking:B-901 <new-value-version-13>
EXEC
~~~~

Nếu key đổi trước EXEC, optimistic transaction có thể không được áp dụng theo WATCH semantics.

Nhưng:
- Phải xử lý CAS conflict.
- Multi-key Redis Cluster có same-slot constraints.
- WATCH không tự tạo siblings/history/CRDT.
- Durability qua failover có policy riêng.
- External payment không nằm trong Redis transaction.

### 32.1. Một Lua script atomic không là global workflow transaction

Script ở một node/slot không tự bảo vệ Order trong MongoDB, payment provider và các Redis slots khác như một transaction chung.

### 32.2. Offline intent vẫn cần metadata

SET mới đến sau không nói server field nào được chỉnh hay client đã thấy revision nào. Phải thiết kế operation/version context trong application.

## 33. CouchDB: revisions và conflict visibility

CouchDB là ví dụ về revision trees và replication conflicts, nơi có thể tồn tại các leaf revisions cạnh tranh. Có thể:
- Có một winning revision phục vụ read mặc định theo policy.
- Có các conflicting revisions cần được truy xuất/resolved qua API phù hợp.
- Có revision ancestry để hiểu conflict lineage.

**Winning revision do engine chọn không tự là business truth**. Một booking hoặc quyền truy cập vẫn cần domain authority.

### 33.1. Revision token không tự là timestamp

Revision ID/token của engine có semantics nội bộ; không lấy “ID lớn hơn” làm chứng minh causality hoặc business recency.

### 33.2. Giữ history không miễn retention

Nếu một bản chứa PII đã phải xóa, application phải đánh giá cả conflict branches, history, backup và replicated copies.

## 34. Riak-style siblings và causal context

Một số distributed key-value designs, lịch sử như Riak, dùng **siblings** cùng vector/dotted version metadata.

Một flow:
1. Client đọc value + context.
2. Client sửa và ghi kèm context đã quan sát.
3. Nếu concurrent với những writes khác, hệ có thể giữ nhiều siblings.
4. Resolver đọc và ghi revision bao trùm các siblings.

Nếu client đã thấy A nhưng **bỏ context**, server có thể không nhận ra B dự định supersede A, tạo siblings không cần thiết.

Dotted version vectors là một họ kỹ thuật để biểu diễn event/causality hiệu quả hơn trong một số mô hình. Không tự xây từ vài counters mà bỏ qua actor lifecycle, retention, membership và dedup.

## 35. Xử lý UNKNOWN sau khi resolution commit

Timeline:

~~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Conflict API
    participant DB as NoSQL authority
    C->>API: Resolve CF-901, opId RES-901
    API->>DB: Conditional commit r24 + ledger
    DB->>DB: Commit
    DB--xAPI: ACK lost
    API-->>C: UNKNOWN
    C->>API: Query/retry same RES-901
    API->>DB: Find operation result
    DB-->>API: COMMITTED r24
    API-->>C: COMMITTED r24
~~~~

**Timeout không chứng minh rollback**. Không tạo RES-902 chỉ vì client không nhận ACK.

### 35.1. Idempotency scope

Quy định:
- OperationId unique trong tenant/entity/workflow nào?
- Same ID + different payload xử lý ra sao?
- Ledger giữ bao lâu?
- Có di chuyển qua shard/region được không?
- Retry từ thiết bị khác có nhận prior result không?
- Concurrent same-ID requests được serialize thế nào?

### 35.2. Read một replica stale không đủ

Nếu client hỏi eventual search không thấy r24, không thể tự kết luận r24 chưa commit. Dùng authoritative operation result/read consistency phù hợp.

## 36. Monitoring conflict phải đo cả mất ý định

| Metric | Ý nghĩa |
| --- | --- |
| Conflict rate / 1.000 writes | Độ phổ biến concurrent edits |
| Siblings per key p95/max | Metadata/payload growth |
| Oldest unresolved age | Conflict backlog |
| Auto merge rate | Số conflict xử lý tự động |
| Manual review count/time | UX/operational load |
| Reopened conflict count | Một resolve bị race với head mới |
| Lost-update incidents | Overwrite im lặng |
| Business invariant violations | Merge sai domain |
| Duplicate operation effects | Retry/dedup lỗi |
| Tombstone resurrection | Delete/retention lỗi |
| Schema incompatibility | Offline clients không tương thích |
| Commit-to-index visibility | Projection lag |
| Conflict resolution p99 | Trải nghiệm lưu/resolve |
| Audit completeness | Có truy nguyên được quyết định không |

### 36.1. Không chỉ đếm ConflictException

Một hệ auto LWW có thể báo conflict=0 nhưng lost updates nhiều. Đo:
- User reports.
- Revision compare histories.
- Business anomalies.
- Unresolved intents bị bỏ.
- Number of field changes superseded.

### 36.2. Bảo mật metrics/logs

Không gắn mọi entityId/userId/operationId thành metric labels. Dùng entity type, policy version, region, shard và top-N; chi tiết nằm trong traces/logs được kiểm soát.

## 37. Fault injection: kiểm chứng ba chiến lược

| Kịch bản | Cách mô phỏng | Tiêu chí đúng |
| --- | --- | --- |
| Two writers same field | Cùng base, hai giá trị khác | Conflict hoặc domain winner có evidence |
| Two writers disjoint fields | Name/phone | Merge chỉ khi field độc lập |
| Cross-field dependency | Room/guestCount | Không tạo booking invalid |
| Clock skew | Một client nhanh 30 phút | Không suy causal order sai |
| Delete–update | Tombstone + stale offline update | Không resurrect ngoài policy |
| Two regions partition | Concurrent accepted intents | Hội tụ đúng, không double confirm |
| CAS race | Hai requests expected v12 | Không silent lost update |
| ACK lost after commit | Drop response resolution | Retry cùng opId trả prior result |
| New head during review | C sửa khi A/B đang resolve | Expected-head guard từ chối stale resolution |
| Duplicate CDC event | Giao eventId ba lần | Một logical effect |
| Out-of-order events | v15 rồi v14 | Projection không đi lùi ngoài contract |
| Old schema client | v1 payload lên server v2 | Upcast/reject, không drop field mù |
| Tombstone GC | Replica offline rồi quay lại | Không resurrect xóa |
| Security revoke/grant | Concurrent ACL edits | Quyền không bị khôi phục sai |
| Double booking | Hai vùng cùng slot | Tối đa một CONFIRMED |
| Wallet concurrent debit | 100−70 và 100−60 | Không confirm trái invariant |
| Index outage | Pause indexer | Source truth không bị thay bằng stale index |
| Hot key conflict storm | Nhiều clients cùng CAS | Bounded retry, conflict UX, p99 |
| Reshard during resolution | Move authority | Ledger/heads không mất/nhân đôi |
| Privacy erase | Xóa revision/backup theo policy | Không lộ PII cũ |

### 37.1. Test history cần ghi

- operationId / revisionId / parentIds.
- Causal context hoặc expectedVersion.
- Invoke/return times.
- Result COMMITTED/CONFLICT/REJECTED/UNKNOWN.
- Source region/shard/authority.
- Final version heads.
- Business invariant checks.
- Event/checkpoint IDs.
- Recovery và retention boundary.

Không coi một timeout thành failed write trong history checker nếu client không biết outcome.

### 37.2. Synthetic benchmark

~~~~yaml
experiment: nosql-conflict-retain-report-merge
actors:
  devices: 1000
  regions: [VN, EU, US]
entities:
  - profile
  - shopping_cart
  - booking
  - inventory
  - access_policy
workload:
  operations:
    - read
    - offline_patch
    - conditional_update
    - delete
    - resolve_conflict
    - replay_projection
  concurrentEditSharePercent: 20
policies:
  - keep_siblings
  - reject_stale
  - three_way_merge
  - domain_merge
  - lww_for_allowed_fields_only
faults:
  - region_partition
  - lost_commit_ack
  - clock_skew
  - out_of_order_delivery
  - offline_client_30_days
  - tombstone_gc_boundary
measure:
  - conflict_count_and_age
  - sibling_count_and_bytes
  - lost_update_rate
  - auto_merge_success
  - invalid_domain_merge
  - double_booking
  - duplicate_operation_effects
  - tombstone_resurrections
  - resolution_p99
  - projection_freshness
~~~~

Đây là spec minh họa, không phải cấu hình chạy trực tiếp trên một NoSQL engine.

## 38. Runbook khi conflict backlog tăng

### Bước 1 — Xác định quy mô

- Những entity/tenant/region nào?
- Bao nhiêu conflict, oldest age và siblings per key?
- Có một offline sync burst hoặc region recovery?
- Có schema/merge policy mới triển khai?
- Có clients không gửi baseRevision?

### Bước 2 — Phân loại

- Same-field conflict.
- Field-disjoint auto-merge candidate.
- Delete/update.
- Booking/inventory/security/financial high-risk.
- Duplicate/late events.
- Incompatible schema.

Không auto merge tất cả chỉ để giảm một con số monitoring.

### Bước 3 — Ngăn phát sinh mới

- Sửa clients bỏ causal token.
- Dùng read-your-writes ở đường edit khi có thể.
- Không dùng stale search làm base.
- Stable operationId và bounded retry.
- Admission/backoff cho offline sync burst.
- Quy tắc routing/authority rõ.

### Bước 4 — Resolve

- Auto merge nhóm đã chứng minh an toàn.
- Domain validation trước commit.
- CAS expected head set.
- Manual review cho nhóm high-risk.
- Audit policy version.
- Quarantine malformed/old-schema edits.

### Bước 5 — Đồng bộ lại

- Xác nhận CDC checkpoints.
- Replay/index rebuild khi cần.
- Kiểm tra tombstone retention.
- Reconcile source vs projections.
- Throttle backfill để không tạo noisy neighbor.

### Bước 6 — Đóng incident

- Conflict backlog về ngưỡng.
- Không có lost updates/duplicate booking/debit.
- Không có delete resurrection.
- Sync p99/freshness đạt SLO.
- Tenant/security isolation đúng.
- Có postmortem về client, causality và rules.

## 39. Những nhầm lẫn thường gặp

1. **“Có replication thì database tự giải quyết mọi conflict đúng.”** Convergence khác domain correctness.
2. **“Timestamp mới nhất là ý định mới nhất.”** Không có causal proof.
3. **“Server nhận cuối nghĩa client đã thấy bản trước.”** Network có thể reorder.
4. **“Vector clock tự biết giá đúng.”** Chỉ biết quan hệ causality.
5. **“Lamport clock phát hiện đầy đủ concurrent writes.”** Không.
6. **“Có MVCC thì client luôn thấy siblings.”** MVCC nội bộ khác conflict API.
7. **“Giữ revisions là tự có authoritative state.”** Cần head/resolution.
8. **“LWW không có conflict nên an toàn.”** Có thể silent lost update.
9. **“Field khác nhau luôn merge được.”** Có invariant liên field.
10. **“Union mọi sets tốt.”** Remove/ACL semantics có thể khác.
11. **“Counter CRDT giữ stock không âm.”** Không nếu không có rights/authority.
12. **“Cart merge giống checkout.”** Ý định khác tài nguyên có hạn.
13. **“Hai order khác ID không có conflict.”** Có thể cùng slot/inventory.
14. **“Atomic increment là exactly-once.”** ACK loss + retry có thể tăng hai lần.
15. **“DELETE nghĩa không còn bản ghi nên khỏi tombstone.”** Stale replica có thể resurrect.
16. **“Tombstone TTL ngắn luôn tốt.”** Có thể phá recovery khi offline lâu.
17. **“409 và 412 là một.”** Precondition vs domain conflict.
18. **“Nếu 412 cứ đổi expectedVersion rồi PUT lại.”** Bỏ qua ý định/bất biến.
19. **“UI chỉ cần nói Save failed.”** Có thể mất local edits.
20. **“Resolve xong không thể có head mới.”** Có thể race.
21. **“Không cần opId cho resolution.”** ACK có thể mất.
22. **“Search không thấy nghĩa source chưa commit.”** Index async.
23. **“Read follower bất kỳ đủ mới để merge.”** Có stale reads.
24. **“Event log không nhận trùng.”** Delivery/replay có thể duplicate.
25. **“Version integer toàn cục đủ cho multi-leader.”** Hai vùng cùng v13.
26. **“Same version number là same content.”** Cần unique revision ID/lineage.
27. **“Schema mới cứ drop fields cũ.”** Có thể mất semantic intent.
28. **“Random winner vẫn hội tụ.”** Replicas có thể chọn khác nhau.
29. **“Merge policy không cần versioning.”** Replay khác outcome.
30. **“Manual resolution được bỏ qua validation.”** Không.
31. **“Một document atomic nghĩa cross-shard workflow atomic.”** Không.
32. **“Cassandra QUORUM tự là LWT.”** Không.
33. **“DynamoDB global mọi cấu hình cùng conflict policy.”** Không.
34. **“Redis WATCH tự lưu history.”** Không.
35. **“CouchDB winning revision tự là business truth.”** Không.
36. **“Giữ siblings nghĩa giữ PII mãi mãi.”** Phải tuân retention/erase.
37. **“Conflict rate=0 chứng minh không lost update.”** LWW có thể che xung đột.
38. **“Version merge càng tự động càng tốt.”** High-risk operations cần authority.
39. **“Có operation intent là khỏi cần idempotency.”** Retry vẫn cần dedup.
40. **“Causal token client gửi là đáng tin tuyệt đối.”** Cần auth/integrity.

## 40. Bài tập: đồng bộ hồ sơ và booking ba vùng

Giả sử SaaS có:
- VN, EU, US.
- Profile edits được chấp nhận khi offline.
- Booking chỉ CONFIRMED ở source có thẩm quyền.
- Search cập nhật bất đồng bộ.
- Client có thể offline 30 ngày.
- Transaction/OperationResult lưu ở NoSQL source.
- Audit/PII retention có giới hạn.
- Java 21 là tầng service.

### Phần A — Hai edits khác field

Base r10:

~~~~json
{"name":"An","phone":"111","notifications":["EMAIL"]}
~~~~

Phone đổi phone sang 222. Laptop thêm PUSH notifications. Cả hai dựa r10.

1. Vẽ revision DAG.
2. Hai updates concurrent hay sequential?
3. Có thể auto merge gì?
4. Notifications remove/add nên dùng policy nào?
5. Tạo revision merged có cả hai parent IDs.

### Phần B — Same-field conflict

Phone đổi name="Bình"; laptop đổi name="Bảo", cùng r10.

1. LWW làm mất điều gì?
2. Trình bày UI base/local/remote.
3. Dùng ETag/If-Match để phát hiện như thế nào?
4. Khi user bấm resolve nhưng ACK mất, cần operationId gì?
5. Vì sao search chưa thấy không chứng minh resolution thất bại?

### Phần C — Vector clocks

Cho:

~~~~text
V1={A:3,B:1,C:0}
V2={A:2,B:2,C:0}
V3={A:3,B:2,C:1}
~~~~

1. Quan hệ V1 với V2?
2. V1 với V3?
3. V2 với V3?
4. Cặp nào concurrent?
5. Vector sau khi quan sát cả V1/V2 cần giữ những component nào?

**Gợi ý:** V1 và V2 concurrent; V3 causally after cả hai trong ví dụ.

### Phần D — Delete/update

VN xóa DOC-9 ở r13a. EU offline sửa r13b dựa trên r12.

1. Delete-wins cho kết quả gì?
2. Keep-siblings cần giữ tombstone thế nào?
3. Nếu offline window 30 ngày nhưng tombstone GC sau 7 ngày, rủi ro gì?
4. Privacy erase làm policy thay đổi ra sao?
5. Người dùng restore phải thực hiện như một operation mới thế nào?

### Phần E — Booking slot

Hai khách cùng đặt R-08 ngày 15/12.

1. Vì sao merge union hai bookings là sai?
2. Slot conditional guard bảo vệ gì?
3. Phân biệt booking intent với confirmed booking.
4. Retry khi ACK mất phải giữ operationId ra sao?
5. Escrow rights giúp gì với quota có thể phân bổ và không phù hợp với một slot duy nhất thế nào?

### Phần F — Giỏ hàng

Base SKU-9 quantity=1. Hai thiết bị bấm +1.

1. MAX hai snapshots bằng bao nhiêu?
2. SUM hai snapshots bằng bao nhiêu?
3. Delta operations có IDs cho kết quả đúng kỳ vọng bao nhiêu?
4. Remove concurrent increment xử lý thế nào?
5. Tại sao checkout vẫn kiểm tra stock?

### Phần G — Java

Thiết kế:
- UpdateOutcome sealed interface.
- CAS theo expectedVersion.
- API GET current heads.
- API POST resolve conflict.
- ResolutionOperationId ledger.
- Domain validator.
- Retry UNKNOWN không tạo duplicate.

Giải thích rõ Conflict khác Unknown.

### Phần H — Engine comparison

Lập bảng:
- MongoDB version field/transactions.
- Cassandra timestamp ordinary writes và LWT.
- DynamoDB conditional writes/global replication.
- Redis WATCH.
- CouchDB revision trees.

Với mỗi engine nêu **có tự expose siblings không**, cách CAS, cách lưu application history và xử lý lost ACK.

### Phần I — Fault injection

Thiết kế test:
1. Two writers same base/same field.
2. Two writers disjoint fields.
3. Clock skew +30 phút.
4. Delete vs update.
5. Out-of-order CDC.
6. Duplicate eventId.
7. Resolution ACK lost.
8. New head during review.
9. Offline quá retention.
10. Permission revoke vs grant.
11. Leader failover trong CAS.
12. Search index lag.

Với mỗi test, ghi:
- Expected outcome.
- Business invariant.
- Source truth.
- Head/revision context.
- Pass/fail evidence.

### Phần J — Phản biện

Một đồng nghiệp đề xuất:

> “Cứ lấy timestamp mới nhất, ghép các JSON fields khác nhau, không cần hỏi người dùng. DELETE thì remove key ngay, không cần tombstone. Nếu thiếu một bản ở search thì cứ retry tạo bản mới.”

Phản biện bằng causal ordering, field dependencies, lost update, tombstone resurrection, source/index distinction, idempotency và business correctness.

### Hướng giải

Một thiết kế hợp lý có thể:
- Giữ **base/local/remote** hoặc siblings khi concurrency chưa phân giải.
- CAS/ETag để phát hiện stale writes ở authority.
- Auto merge **field độc lập đã qua domain validation**.
- Báo conflict cho same-field/high-risk changes.
- Dùng CRDT cho các semantics cho phép, không cho stock/booking/balance tùy tiện.
- Giữ tombstones/retention đúng với offline/repair.
- Ghi resolution với expected heads, operationId và outbox.
- Đo conflict age, lost updates, duplicate effects, projection lag và invariants.

## 41. Checklist thiết kế trước production

1. **Những entity nào có concurrent/offline writes?**
2. **Causal context/revision token là gì?**
3. **Có phân biệt concurrent với causally later không?**
4. **Client có lưu baseRevision và stable operationId không?**
5. **Read dùng để resolve có đủ mới không?**
6. **Có fields nào được phép LWW?**
7. **Những fields nào cần giữ siblings/history?**
8. **Có conflict API/UX rõ không?**
9. **ETag/If-Match/409/412 semantics đã thống nhất?**
10. **Có CAS/transaction guard ngăn lost update?**
11. **Field merge có phân biệt missing/null/remove không?**
12. **Có domain validation sau structural merge không?**
13. **Shopping cart và inventory có semantics khác nhau không?**
14. **Booking slot có một authority hoặc rights protocol?**
15. **Finance có ledger/idempotency không?**
16. **ACL revoke có policy an toàn không?**
17. **Delete có tombstone/chống resurrection?**
18. **Tombstone retention đủ cho offline/repair không?**
19. **Privacy erasure bao phủ revisions/backups không?**
20. **Resolution request có idempotency và fingerprint?**
21. **Expected-head set có được kiểm tra atomically?**
22. **Schema/policy versions được lưu không?**
23. **Resolver deterministic khi replay không?**
24. **CDC consumers dedup/out-of-order đúng không?**
25. **Read models có freshness SLO riêng?**
26. **Có giới hạn sibling count/metadata growth?**
27. **Conflict review/escrow/quarantine có vận hành được?**
28. **Metrics có lost updates và invalid merges, không chỉ conflict count?**
29. **Có auth/tenant isolation khi xem revision history?**
30. **Có fault injection partition, clock skew, ACK loss, tombstone GC?**

**Kết luận:** Khi các bản sao NoSQL và thiết bị offline cùng sửa một đối tượng, không nên coi **bản có timestamp mới nhất** là câu trả lời duy nhất. **Giữ nhiều phiên bản** bảo vệ những ý định chưa thể phân xử, **báo xung đột** giúp client và người dùng không bị ghi đè âm thầm, còn **hợp nhất theo nghiệp vụ** cho phép tự động xử lý chỉ khi semantics và invariant đều đúng. Causal metadata, vector clocks, version tokens và ETag/CAS hỗ trợ phát hiện và kiểm soát cạnh tranh; CRDT hỗ trợ hội tụ trong một số domain; nhưng booking, tồn kho, tài chính và quyền truy cập vẫn cần authority hoặc cơ chế phân bổ quyền phù hợp. Mỗi resolution phải là **một commit mới được validate, gắn lineage và operationId**, đồng thời xử lý tombstone, retry ACK loss, CDC lag và schema evolution. Hãy kiểm chứng bằng **lịch sử concurrent edits, partition, clock skew, duplicate delivery, delete resurrection và business invariants**, chứ không chỉ bằng tỷ lệ API thành công.
