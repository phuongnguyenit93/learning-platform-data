# Đồng bộ hai chiều, xóa dữ liệu và tránh khôi phục bản cũ ngoài ý muốn

Một ứng dụng ghi chú lưu dữ liệu ở **máy chủ NoSQL** và trên nhiều điện thoại/laptop. Người dùng có thể chỉnh sửa khi offline, sau đó các thiết bị **đồng bộ hai chiều**: gửi những thay đổi cục bộ lên server và nhận những thay đổi từ server về thiết bị.

Giả sử điện thoại A xóa ghi chú **note-42** lúc 09:00. Laptop B mất mạng từ hôm trước nên vẫn giữ nội dung cũ. Một tuần sau, B kết nối lại và gửi bản ghi note-42 lên server. Nếu server chỉ so sánh “bản ghi nào tồn tại” và sao chép dữ liệu từ B sang, **ghi chú đã bị xóa xuất hiện trở lại**. Đó là lỗi **resurrection** hay **zombie record**: dữ liệu cũ bị hiểu nhầm là một thao tác tạo/cập nhật mới hợp lệ.

Không thể xử lý đúng bài toán này bằng cách “đợi đồng bộ lâu hơn” hoặc “mỗi bên gửi toàn bộ dữ liệu cho bên kia”. Khi một bản ghi **không còn tồn tại**, hệ thống phải phân biệt ít nhất hai trường hợp:

- Bản ghi **chưa từng tồn tại ở nơi đang đọc**, có thể cần được tạo từ bản sao khác.
- Bản ghi **đã bị xóa có chủ đích**, nên bản sao cũ **không được phép khôi phục** nếu không có hành động tạo lại hợp lệ.

Sự khác nhau ấy thường được biểu diễn bằng **tombstone (dấu xóa), phiên bản/quan hệ nhân quả, operation ID, changelog và quy tắc merge**. Ngoài ra còn có bài toán khó: tombstone có thể lưu trong bao lâu khi một client có khả năng offline rất lâu, hoặc khi database bị restore từ backup cũ?

Bài học này thuộc chương **Xung đột và đồng bộ** của module **Database No SQL**. Ta sẽ thiết kế giao thức đồng bộ hai chiều, mô tả timeline gây resurrection, cách giải quyết delete–update concurrent, version vector, anti-entropy, change-feed checkpoint, retention và garbage collection an toàn; minh họa trên CouchDB, MongoDB, Cassandra, DynamoDB, Redis và các hệ offline-first. Phần cuối có quy trình vận hành, kiểm thử lỗi và bài tập thực hành.

## 1. Đồng bộ hai chiều thực chất là gì?

**Bidirectional synchronization** nghĩa là hai phía có thể đồng thời là **nguồn phát sinh thay đổi** và **nơi nhận thay đổi**.

Ví dụ:

~~~text
Điện thoại A  --push updates-->  Server
Điện thoại A  <--pull updates--  Server

Laptop B      --push updates-->  Server
Laptop B      <--pull updates--  Server
~~~

Ứng dụng mong các bên cuối cùng hội tụ về trạng thái phù hợp khi mạng ổn định và việc đồng bộ hoàn tất. Nhưng **hội tụ** khác **đúng nghiệp vụ**: mọi thiết bị cùng giữ một bản ghi lẽ ra phải bị xóa vẫn là một trạng thái hội tụ sai.

Đồng bộ hai chiều cần trả lời:

1. Đối tượng dữ liệu được nhận diện bằng **ID nào**?
2. Mỗi thay đổi mang **version, operation ID và actor identity** ra sao?
3. Làm sao biết bản A mới hơn bản B, hay chúng **concurrent**?
4. Một **DELETE** được truyền dưới dạng dữ liệu gì?
5. Khi DELETE và UPDATE xảy ra cùng lúc, ai thắng?
6. Làm sao không **áp dụng một thay đổi hai lần** khi push/pull/retry?
7. Thiết bị offline quá lâu được đồng bộ tăng dần hay buộc **full resync**?
8. Khi nào được dọn tombstone mà không tạo điều kiện hồi sinh dữ liệu cũ?

Một hệ đồng bộ đúng phải có câu trả lời cụ thể cho từng điểm; tên “eventual consistency” không thay thế bản thiết kế.

## 2. Replication, cache và offline synchronization có khác nhau?

| Cơ chế | Nơi phát sinh ghi | Đặc điểm quan trọng |
|---|---|---|
| **Leader–follower replication** | Thường một leader cho mỗi phạm vi | Follower học thay đổi theo protocol của database |
| **Multi-leader replication** | Nhiều leader/vùng có thể chấp nhận ghi | Cần phát hiện hoặc giải quyết concurrent writes |
| **Leaderless replication** | Nhiều replica/coordinator nhận write theo policy | Version conflict, read repair, anti-entropy |
| **Client–server offline sync** | Thiết bị và server đều có thể thay đổi | Thiết bị có thể biến mất lâu, quay lại với dữ liệu cũ |
| **Cache invalidation** | Nguồn dữ liệu có thẩm quyền, cache chứa bản tạm | DELETE cần làm cache không trả value cũ |
| **Read model/materialized view** | Nguồn phát event, view được dựng lại | Xóa phải được lan truyền như một thay đổi, không chỉ bỏ event |

Các hệ có thể kết hợp: MongoDB replica set bảo vệ database nguồn, ứng dụng mobile đồng bộ qua API riêng, còn Redis chỉ giữ cache. Bản ghi “không có” ở MongoDB và một object còn trong cache là hai lớp khác nhau cần xử lý.

**Không phải cứ hai database có replication với nhau là application có offline conflict semantics đúng.** Đồng bộ theo row, theo event và theo CRDT có những hợp đồng khác nhau.

## 3. Minh họa kiến trúc đồng bộ hai chiều

~~~mermaid
flowchart LR
    A["Thiết bị A\nLocal store + outbox"] <-->|"Push/Pull"| G["Sync API"]
    B["Thiết bị B\nLocal store + outbox"] <-->|"Push/Pull"| G
    G --> S["Authoritative NoSQL state"]
    G --> C["Change log / tombstones"]
    C --> G
    S --> C
~~~

Trong một thiết kế **server-authoritative** điển hình:

- Thiết bị lưu **working copy** phục vụ offline.
- Thao tác cục bộ được ghi vào **outbox** cùng operationId.
- Khi có mạng, thiết bị **push** các thao tác chưa xác nhận.
- Server kiểm tra quyền, phiên bản và quy tắc conflict trước khi nhận.
- Server ghi thay đổi vào nguồn dữ liệu và **change log** theo cơ chế đáng tin.
- Thiết bị **pull** các thay đổi từ một checkpoint và áp dụng vào local store.

Một số hệ là **peer-to-peer** hoặc multi-master thuần túy, không có một server quyết định mọi conflict. Khi đó cần protocol merge có thể hội tụ, ví dụ version vectors/CRDT. Nhưng dù là kiến trúc nào, **DELETE vẫn phải có representation và quy tắc giữ lại**.

## 4. Một timeline gây resurrection dù không có lỗi chương trình rõ ràng

~~~text
Ngày 01, 08:00
  Server: note-42 = "Kế hoạch A", version 5
  Thiết bị A: version 5
  Thiết bị B: version 5

Ngày 01, 09:00
  A gửi DELETE note-42.
  Server xóa vật lý record và trả OK.
  A không còn note-42.

Ngày 08, 10:00
  B online sau 7 ngày.
  B push toàn bộ local notes.
  B gửi note-42 = "Kế hoạch A", version 5.

Server nhìn thấy:
  note-42 không tồn tại.

Server tự tạo:
  note-42 = "Kế hoạch A".
~~~

Trong tình huống này:

- DELETE ban đầu hoàn toàn có thể đã thành công.
- Không có mạng nào bắt buộc phải gửi trùng dữ liệu.
- Lỗi nằm ở **quy tắc merge “missing = chưa có”**.

Muốn ngăn, server phải có bằng chứng rằng **note-42 từng tồn tại và đã bị xóa**; đồng thời cần phân biệt **bản cũ version 5** với một yêu cầu **tạo mới có chủ đích** sau khi xóa.

## 5. DELETE là một sự kiện chứ không chỉ là khoảng trống

Với một dữ liệu sống:

~~~json
{
  "id": "note-42",
  "content": "Kế hoạch A",
  "revision": 5,
  "deleted": false
}
~~~

Một DELETE có thể được biểu diễn dưới dạng **tombstone**:

~~~json
{
  "id": "note-42",
  "revision": 6,
  "deleted": true,
  "deletedAt": "2026-11-14T09:00:00Z",
  "deleteOperationId": "delete-note-42-e91"
}
~~~

Tombstone vẫn là một **trạng thái có danh tính và phiên bản**. Khi B gửi version 5, server có thể trả rằng **revision 6 là thao tác xóa mới hơn** thay vì create record.

Các thuật ngữ liên quan:

- **Soft delete:** đánh dấu record không còn hiển thị nhưng có thể còn nội dung.
- **Tombstone:** metadata biểu thị delete trong replication/merge protocol.
- **Hard delete/physical purge:** xóa bytes hoặc đối tượng khỏi một phạm vi lưu trữ cụ thể.
- **Logical deletion:** không còn được coi là bản ghi sống trong API.
- **Deletion propagation:** lan truyền hiệu ứng xóa tới replicas, caches và downstream.
- **Garbage collection:** dọn tombstone sau khi an toàn theo policy.

**Soft delete và tombstone không luôn đồng nghĩa.** Một record mềm vẫn chứa nội dung đầy đủ; tombstone có thể chỉ giữ ID, version và metadata tối thiểu.

## 6. Bản ghi thiếu không thể thay thế delete marker

Giả sử hệ chỉ truyền **snapshot các record còn sống**:

~~~text
Snapshot A: [note-1, note-2]
Snapshot B: [note-1, note-2, note-42]
~~~

Không có thông tin nào trong snapshot A chứng minh note-42:

- Đã bị xóa.
- Chưa bao giờ thuộc phạm vi đồng bộ của A.
- Bị ẩn do permission/filter.
- Chưa được tải vì phân trang.
- Đang tạm không trả vì lỗi truy vấn.

**Phép đồng bộ kiểu lấy hợp (union)** sẽ đưa note-42 trở lại. **Phép đồng bộ kiểu lấy giao (intersection)** có thể xóa nhầm dữ liệu hợp lệ chưa tải ở một phía.

Do đó một giao thức đáng tin cần **change events**, **tombstone**, **versioned snapshots**, hoặc một protocol reconciliation đủ khả năng giải quyết sự vắng mặt một cách có nghĩa.

## 7. Danh tính đối tượng phải ổn định qua xóa và tạo lại

Ví dụ:

~~~text
noteId = note-42
~~~

Nếu note-42 bị xóa ở revision 6, một client cũ có thể gửi:

~~~text
UPSERT noteId=note-42, revision=5
~~~

Server phải xem đây là **cập nhật lỗi thời**, không phải một CREATE hợp lệ chỉ vì không còn row sống.

Nếu người dùng cố ý tạo một ghi chú mới sau khi xóa, cần một hợp đồng rõ:

**Cách 1 — ID mới:**

~~~text
Old: note-42 (deleted)
New: note-99
~~~

**Cách 2 — Cùng logical ID nhưng generation mới:**

~~~text
(noteId=note-42, generation=1) DELETED
(noteId=note-42, generation=2) LIVE
~~~

Generation phải được cấp/kiểm theo authority để client cũ không tự tăng và hồi sinh nội dung trái ý định. Điều này đặc biệt cần khi ID được derive từ tên file, username, đường dẫn hoặc entity key tái sử dụng.

## 8. Ba quan hệ phiên bản cần phân biệt

Khi so hai cập nhật cho cùng một đối tượng, ta cần biết:

1. **A xảy ra trước B theo quan hệ nhân quả (A → B)**: B biết hiệu ứng của A.
2. **B xảy ra trước A**: A biết hiệu ứng của B.
3. **A và B concurrent**: không bên nào quan sát thay đổi kia trước khi ghi.

Ví dụ:

~~~text
Server note v5
  |
  +--- A DELETE note, dựa trên v5
  |
  +--- B UPDATE content, cũng dựa trên v5
~~~

DELETE của A và UPDATE của B là **concurrent**; không thể chỉ dùng con số “v6” tùy ý của mỗi client rồi nói chắc thao tác nào xảy ra sau theo quan hệ nhân quả.

Như vậy quy tắc cho **update cũ sau delete** và quy tắc cho **delete concurrent với update** là hai bài toán khác nhau.

## 9. Version đơn điệu tại một nguồn có thẩm quyền

Trong hệ có **server là authority** cho từng record, server có thể cấp **revision tăng**:

~~~text
revision 10: CREATE
revision 11: UPDATE
revision 12: DELETE
~~~

Client push update phải cung cấp:

~~~json
{
  "id": "note-42",
  "baseRevision": 10,
  "operationId": "edit-abc",
  "type": "UPDATE",
  "content": "Kế hoạch B"
}
~~~

Server hiện có tombstone revision 12. Predicate:

~~~text
IF currentRevision == baseRevision
THEN apply mutation and issue next revision
ELSE return CONFLICT / STALE_BASE
~~~

vì 12 không bằng 10, ghi cũ bị chặn.

**Revision check phải được thực hiện nguyên tử với mutation**. Nếu ứng dụng làm GET revision rồi UPDATE không điều kiện, thay đổi khác có thể chen vào giữa.

## 10. Version vector để biểu diễn quan hệ nhân quả

Trong hệ **multi-writer**, một scalar revision do từng thiết bị tự tăng có thể đụng nhau:

~~~text
Server v5
A offline -> edit A v6
B offline -> edit B v6
~~~

Hai v6 không chứng minh một bản mới hơn bản còn lại. Một **version vector** minh họa:

~~~text
Base:
  {A:2, B:4}

A xóa sau khi nhìn Base:
  {A:3, B:4}

B sửa độc lập từ Base:
  {A:2, B:5}
~~~

Hai vector mới là **concurrent** vì không vector nào lớn hơn hoặc bằng vector kia theo tất cả thành phần.

Nếu một phiên bản:

~~~text
{A:3, B:5}
~~~

được hình thành sau khi quan sát cả hai nhánh theo giao thức version vector đúng, nó có thể biểu diễn trạng thái đã biết cả hai thay đổi.

**Vector clock/version vector phát hiện causality hoặc concurrency**, nhưng **không chọn giúp** nên giữ delete hay edit. Quyết định đó là **conflict policy** của dữ liệu.

## 11. Đồng hồ tường và Last-Write-Wins dễ dẫn đến hồi sinh sai

Một chiến lược phổ biến:

~~~text
newer timestamp wins
~~~

Ví dụ:

~~~text
09:00 thực tế: A DELETE note-42, timestamp thiết bị A = 09:00.
09:05 thực tế: B online với bản cũ v5.
             Đồng hồ B bị chỉnh nhanh tới 11:00.
             B UPSERT note-42, timestamp = 11:00.
~~~

Nếu hệ lấy **timestamp lớn nhất** mà không xét quan hệ nhân quả/delete, bản cũ có thể “thắng” và note-42 sống lại.

Ngay cả khi đồng hồ đồng bộ khá tốt, **event đến sau** không đồng nghĩa **ý định sửa xảy ra sau delete**: B có thể đang gửi queue các thao tác offline từ ngày trước.

Last-write-wins (LWW) có thể phù hợp một số field như theme của UI nếu chấp nhận mất chỉnh sửa. Nhưng với delete, quyền riêng tư hoặc quan hệ nghiệp vụ, cần nêu rõ:

- “Last” theo **timestamp nào**?
- DELETE có được ưu tiên không?
- Một update stale được nhận hay bị reject?
- Client clock có được tin không?
- Có cơ chế tạo lại có chủ đích không?

**Đặt updatedAt mới khi upload dữ liệu cũ** là một cách rất dễ khiến dữ liệu đã xóa bị xem như bản ghi mới.

## 12. Delete-wins, update-wins và conflict thủ công

Khi DELETE và UPDATE **concurrent**, không có một chính sách đúng cho mọi nghiệp vụ.

| Policy | Kết quả khi delete và update concurrent | Phù hợp khi |
|---|---|---|
| **Delete-wins/remove-wins** | Đối tượng vẫn bị xóa | Quyền riêng tư, người dùng mong xóa ưu tiên |
| **Update-wins/add-wins** | Giữ lại phiên bản được sửa trong tình huống được định nghĩa | Dữ liệu hợp tác, muốn tránh mất edit |
| **Manual conflict** | Giữ conflict metadata, hỏi người dùng | Tài liệu có giá trị, không muốn tự bỏ thao tác |
| **Owner-based** | Owner/role được xác định quyết định | Dữ liệu có phân quyền rõ |
| **Field-level merge** | Một số fields được gộp, delete được xử lý riêng | Schema có semantics độc lập |

Một ứng dụng ghi chú cá nhân có thể chọn **delete-wins**. Một trình soạn tài liệu cộng tác có thể tạo thông báo “bạn đã sửa một tài liệu vừa bị xóa; khôi phục thành bản mới hay bỏ bản sửa?”.

**Không tự khôi phục âm thầm** chỉ vì muốn tránh mất thay đổi. Nếu cho người dùng khôi phục, đó phải là một hành động mới có identity/generation, quyền và audit rõ ràng.

## 13. Delete có nhiều nghĩa nghiệp vụ

Những hành động cùng hiển thị nút “Xóa” có thể khác:

1. **Hide for me:** chỉ ẩn khỏi danh sách của một user; object vẫn sống.
2. **Remove relationship:** bỏ liên kết user–object, chưa xóa object chia sẻ.
3. **Archive:** đổi trạng thái để không hiển thị mặc định.
4. **Delete shared object:** xóa object đối với mọi collaborator.
5. **Erase personal data:** phải xử lý các bản sao/nguồn chứa dữ liệu theo policy.
6. **Revoke access:** cấm user hoặc thiết bị đọc tiếp, dù dữ liệu còn được giữ hợp lệ ở nơi khác.

Nếu client A chỉ “ẩn ghi chú khỏi danh sách của A”, client B vẫn còn ghi chú **không phải resurrection**. Vì thế mọi delete operation phải có **scope**:

~~~json
{
  "operationId": "delete-abc",
  "objectId": "note-42",
  "type": "DELETE_SHARED_OBJECT",
  "scope": "workspace-7",
  "actorId": "user-11",
  "baseRevision": 18
}
~~~

Server phải kiểm quyền của actor tại thời điểm commit theo contract. Một tombstone không đồng nghĩa “mọi bản sao vật lý đã bị xóa ngay lập tức”.

## 14. Vì sao tombstone phải có phiên bản?

Một tombstone chỉ gồm:

~~~json
{"id":"note-42","deleted":true}
~~~

có thể chưa đủ để so sánh với UPDATE đến muộn. Nên có:

~~~json
{
  "id": "note-42",
  "generation": 1,
  "revision": 19,
  "deleted": true,
  "deleteOperationId": "del-5501",
  "origin": "server",
  "deletedAt": "2026-11-14T09:00:00Z"
}
~~~

Những fields cần xem:

- **Object ID**: đúng đối tượng cần xóa.
- **Generation/epoch**: phân biệt tạo lại hợp lệ với bản cũ.
- **Revision/causal metadata**: xác định stale hay concurrent.
- **Delete operation ID**: chống áp dụng trùng và audit.
- **Scope/tenant**: ngăn delete lan sang khách hàng khác.
- **Server commit sequence**: phục vụ change feed/checkpoint.
- **Retention metadata**: dùng để dọn an toàn, không thay thế kiểm tra replication state.

Tombstone có thể **không giữ payload gốc**. Đó là lợi thế về quyền riêng tư và dung lượng, miễn đủ thông tin để chặn bản cũ.

## 15. Một state machine cho đối tượng có thể được xóa

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> LIVE: CREATE generation 1
    LIVE --> LIVE: UPDATE with expected revision
    LIVE --> DELETED: DELETE revision 19
    DELETED --> DELETED: retry DELETE same operation
    DELETED --> LIVE_NEW_GENERATION: explicit RECREATE
    LIVE_NEW_GENERATION --> LIVE_NEW_GENERATION: UPDATE
    LIVE_NEW_GENERATION --> DELETED: DELETE generation 2
~~~

Lưu ý:

- **ABSENT** không đồng nghĩa **DELETED** nếu chưa có lịch sử.
- **DELETED → LIVE_NEW_GENERATION** là một thao tác nghiệp vụ riêng, không phải upsert stale.
- **LIVE_NEW_GENERATION** được hiểu là live object với generation mới; hệ có thể ghi lại trạng thái là LIVE kèm generation.
- Retry delete cùng operationId phải idempotent; không làm tăng generation hoặc phát side effect lặp.

Trong một hệ cần cấm hoàn toàn việc tái sử dụng ID, có thể bỏ transition **RECREATE** và bắt buộc CREATE dùng ID khác.

## 16. Thiết kế đường push thay đổi

Client local outbox:

~~~json
{
  "clientId": "phone-A",
  "operationId": "op-8801",
  "objectId": "note-42",
  "type": "DELETE",
  "baseRevision": 18,
  "generation": 1,
  "localSequence": 114
}
~~~

Quy trình push:

1. Client giữ operationId ổn định qua retry.
2. Server xác thực tenant, actor, object và quyền ghi.
3. Server tra **authoritative object/tombstone** cùng phiên bản.
4. So baseRevision/causal metadata và chạy conflict policy.
5. Ghi **state mutation + change event + operation outcome** trong một atomic unit hoặc protocol recoverable.
6. Trả **server revision/commit cursor**.
7. Client đánh dấu local outbox operation đã được công nhận, không tự đổi operationId nếu response mất.

Điều kiện quan trọng:

~~~text
Compare current version
AND apply delete/update
AND record result
~~~

phải được bảo vệ chống race. Một **GET rồi UPDATE không điều kiện** trên database ở hai RPC không tự là CAS.

## 17. Thiết kế đường pull thay đổi

Thiết bị B lưu:

~~~text
lastServerCursor = 5021
~~~

Server có change feed:

~~~text
5022: note-12 UPDATE rev 7
5023: note-42 DELETE rev 19
5024: note-99 CREATE rev 1
~~~

Client:

~~~text
PULL after cursor 5021
  -> nhận 5022, 5023, 5024
  -> áp dụng từng thay đổi an toàn vào local store
  -> lưu cursor 5024
~~~

Tại **5023**, B không chỉ “bỏ qua vì không còn data”. B phải xóa/đánh dấu local note-42, xử lý thay đổi cục bộ đang pending và ghi nhận version thích hợp để không push bản v5 như một update mới.

**Cursor là checkpoint của dòng thay đổi**, không tự là timestamp đồng hồ. Một cursor hợp lệ thường gắn với server log/stream và có tính liên tục theo protocol.

## 18. Checkpoint phải được ghi cùng việc áp dụng change

Một client pull hai events:

~~~text
E1: UPDATE note-1
E2: DELETE note-42
~~~

Nếu client ghi:

~~~text
lastCursor = after E2
~~~

rồi crash **trước khi áp dụng E2**, khi restart nó có thể bỏ qua DELETE vĩnh viễn.

Giao thức local cần:

~~~text
Atomic local transaction:
  apply E1/E2
  save lastCursor
COMMIT
~~~

hoặc lưu per-event processing markers/checkpoints để replay an toàn.

Nếu local store không hỗ trợ transaction, chọn cách xử lý **at-least-once + idempotent apply**:

- Chỉ advance cursor sau khi chắc chắn event đã áp dụng bền vững.
- Khi restart có thể nhận lại event cũ.
- Apply event phải so version/operationId để không lặp hiệu ứng.

**Checkpoint không được vượt qua một lỗ hổng chưa xử lý** nếu giao thức yêu cầu apply theo thứ tự liên tục.

## 19. Không dùng timestamp mơ hồ làm sync cursor

Một API dễ mắc lỗi:

~~~text
GET /changes?updatedAfter=2026-11-14T09:00:00Z
~~~

Vấn đề:

- Nhiều updates có cùng millisecond.
- Đồng hồ các nodes có thể lệch.
- Một transaction commit sau nhưng có client timestamp cũ.
- DELETE đã xóa row nên không nằm trong query updatedAt thông thường.
- Pagination có thể bỏ sót những bản ghi được chèn trong lúc quét.
- Chuyển timezone hoặc độ chính xác thời gian gây biên sai.

Nếu phải dùng time-based pagination, thường cần **tie-breaker và snapshot/high-watermark** được định nghĩa rõ. Tốt hơn trong nhiều trường hợp là sử dụng **monotonic log sequence, change stream token hoặc server-provided opaque cursor**.

Ví dụ:

~~~text
cursor = opaque("partition=p1;sequence=5100;epoch=7")
~~~

Client không tự parse hoặc cộng cursor nếu API coi nó là opaque; phải lưu và gửi lại đúng theo protocol.

## 20. Tránh vòng lặp echo trong đồng bộ hai chiều

Một client pull server event:

~~~text
Server -> A: note-42 DELETE
~~~

Nếu A áp dụng bằng cách gọi một hàm local mặc định “mọi thay đổi local đều thêm vào outbox”, A có thể push lại chính DELETE:

~~~text
A -> Server: note-42 DELETE
Server -> A: note-42 DELETE
...
~~~

Cần phân biệt:

- **Local user-originated mutation**: sinh operationId và thêm outbox.
- **Remote change apply**: cập nhật local materialized state và cursor, **không tạo local intent mới**.
- **Conflict resolution do người dùng chọn**: có thể sinh operation mới với lineage rõ.

Một remote DELETE áp dụng nhiều lần nên **idempotent**; không tạo lại delete operationId mới mỗi lần thấy event cũ.

## 21. Idempotency cho mỗi push operation

Một DELETE được gửi:

~~~text
A push delete(opId=del-5501)
Server commit tombstone.
HTTP response mất.
A push lại del-5501.
~~~

Nếu server tạo một revision mới cho mỗi lần nhận, thay đổi có thể bị phát lại vô hạn hoặc gây conflict không cần thiết.

Một idempotent push:

~~~text
if operationId đã commit:
  verify scope/payload fingerprint
  return original result/revision
else:
  validate and apply state change
  save operation outcome
~~~

Tối ưu nhất khi **state mutation và dedup result** cùng một atomic unit hoặc có recovery protocol tương đương.

Điều này đúng với **UPDATE, DELETE, RECREATE, MOVE và RELATIONSHIP REMOVE**. Trong các hệ eventual, **đã nhận event hai lần** là bình thường; effect không nên bị áp dụng hai lần.

## 22. Giải quyết local pending edit khi remote DELETE đến

B offline sửa note-42:

~~~text
Local note v5:
  content="Kế hoạch A"

Pending local operation:
  EDIT content="Kế hoạch B", basedOn v5
~~~

Trong lúc đó A xóa note-42, server commit tombstone v6.

Khi B pull DELETE và còn EDIT pending, không nên tự:

~~~text
apply DELETE -> remove local
then replay EDIT -> UPSERT note
~~~

Vì như vậy vừa xóa xong lại tự khôi phục.

Các lựa chọn:

1. **Delete-wins:** ghi nhận EDIT đã bị superseded, giữ conflict data tạm để người dùng xem, không push như upsert.
2. **Manual resolution:** hỏi người dùng có muốn tạo **note mới** từ nội dung offline không.
3. **Update-wins:** chỉ nếu contract cho phép một edit concurrent phục hồi đối tượng.
4. **Field-level CRDT:** cho phép merge theo kiểu dữ liệu, nhưng delete object vẫn có semantics riêng.

**Pending edit không được mất im lặng** nếu sản phẩm cam kết giữ bản nháp. Nhưng giữ một bản nháp local riêng khác với tự hồi sinh tài liệu đã xóa ở server.

## 23. Quản lý conflict record tách khỏi record sống

Khi B có edit concurrent với remote delete, có thể lưu:

~~~json
{
  "conflictId": "conflict-710",
  "objectId": "note-42",
  "remoteOperation": "DELETE",
  "remoteRevision": 19,
  "localOperation": "EDIT",
  "localOperationId": "edit-900",
  "resolution": "UNRESOLVED",
  "localDraftReference": "encrypted-local-draft-900"
}
~~~

Lưu ý:

- Không để conflict record tự hiện thành một bản **LIVE note-42**.
- Nội dung nhạy cảm của draft cần encryption, ACL và retention.
- Khi user chọn **Restore as new**, tạo một operation có ID/generation mới, server kiểm quyền như CREATE.
- Nếu delete là yêu cầu **erasure/thu hồi quyền**, có thể không được phép giữ hoặc phục hồi bản nháp; contract và pháp lý phải được xét riêng.

Conflict UI không được trở thành lối đi vòng quy tắc quyền truy cập và xóa dữ liệu.

## 24. CRDT và ý nghĩa “remove”

Trong một số mô hình CRDT, delete có thể được biểu diễn bằng các quy tắc gộp đặc biệt.

Ví dụ một **Observed-Remove Set (OR-Set)** lưu các phần tử cùng những **unique add tags**:

~~~text
Replica A:
  ADD "tag:books" với addTag=a1

Replica B (đã thấy a1):
  REMOVE "tag:books" -> loại a1
~~~

Một remove trong OR-Set kiểu add-wins có thể chỉ xóa những add tags **đã quan sát**. Nếu một replica khác ADD cùng phần tử với tag mới **concurrent**, bản add có thể tồn tại sau merge.

Đó không phải lỗi thuật toán; nó là semantics **add-wins**.

| Tình huống | Add-wins set | Remove-wins set |
|---|---|---|
| REMOVE và ADD cùng phần tử concurrent | Add có thể tồn tại | Remove được ưu tiên theo định nghĩa loại |
| REMOVE xảy ra sau khi thấy ADD | Remove có thể xóa bản đã thấy | Remove có thể xóa |
| ADD có chủ đích sau REMOVE | Có thể tồn tại nếu protocol nhận đó là add mới hợp lệ | Tùy generation/causal protocol |

Không thể nói “CRDT giải quyết mọi conflict” nếu chưa chỉ ra **CRDT loại nào** và **remove-wins hay add-wins** trong yêu cầu nghiệp vụ.

## 25. Delete object khác remove một cạnh quan hệ

Một workspace:

~~~text
Document doc-42
  collaborators = [user-A, user-B]
~~~

Khi user-A chọn **Remove collaborator B**, đó là **xóa quan hệ (doc-42, user-B)**, không phải DELETE doc-42.

Nếu relation được denormalize:

~~~text
doc_collaborators[doc-42] chứa B
user_documents[user-B] chứa doc-42
~~~

thì thao tác cần cập nhật hai read models hoặc phát một event:

~~~json
{
  "eventId": "acl-change-901",
  "type": "COLLABORATOR_REMOVED",
  "documentId": "doc-42",
  "userId": "user-B",
  "revision": 12
}
~~~

Một index cũ ở user_documents có thể tiếp tục hiển thị document, nhưng **không được phép cho user-B đọc nội dung** nếu quyền đã bị thu hồi. Authorization phải được thực thi ở nguồn có thẩm quyền, không chỉ qua read model eventual.

Để tránh “hồi sinh cạnh cũ”, relation cũng cần **identity, version/tombstone hoặc event ordering** của riêng nó.

## 26. Xóa theo cascade và dữ liệu denormalized

Một note có:

~~~text
note primary document
note_by_user index
notes_by_workspace feed
search index
attachments metadata
cache
analytics projection
~~~

DELETE ở nguồn không tự xóa mọi bản:

~~~mermaid
flowchart TD
    D["DELETE note-42 tại nguồn"] --> T["Persist tombstone + delete event"]
    T --> U["User/workspace read models"]
    T --> S["Search index"]
    T --> C["Caches"]
    T --> A["Attachment lifecycle"]
    T --> R["Replication clients"]
    U --> V["Reconciliation / visibility checks"]
    S --> V
    C --> V
    A --> V
    R --> V
~~~

Cần thiết kế:

1. **Authoritative delete commit**.
2. **Outbox/change log** để không mất intent xóa sau commit.
3. **Consumer idempotency** theo delete operationId.
4. **Ordering/version check** để một UPDATE cũ không tạo lại search document.
5. **Retry và dead-letter/backlog recovery**.
6. **Verification** những nơi cần xóa.
7. **Retention/purge** dữ liệu và tombstones theo chính sách.

Trong hệ eventual, một read model có thể còn stale trong một khoảng thời gian, nhưng **truy cập dữ liệu đã bị thu hồi** có thể cần chặn ngay tại authorization path.

## 27. Outbox/inbox cho sự kiện DELETE

Một lỗi:

~~~text
1. Database commit DELETE note-42.
2. Application định publish NoteDeleted.
3. Process crash trước khi publish.
~~~

Nếu không có change feed đáng tin hoặc outbox, downstream không biết phải xóa.

**Transactional outbox**:

~~~text
DB atomic unit:
  update note to tombstone
  append outbox event NoteDeleted(opId, revision)
COMMIT

Relay:
  publish event đến broker
  mark delivered theo checkpoint
~~~

Relay có thể gửi event nhiều lần. Các consumers dùng **inbox/eventId/version guards**, ví dụ:

~~~text
On NoteDeleted(note-42, rev=19):
  if projection revision >= 19:
      ignore as duplicate/stale
  else:
      remove/hide projection
      save projection revision=19 (tombstone)
~~~

Nếu consumer sau đó nhận **NoteUpdated rev=18**, nó phải **bỏ qua**, không tạo lại search document.

**Không chỉ xóa row projection và quên revision**, vì consumer có thể nhận update cũ sau DELETE.

## 28. Anti-entropy và sửa sai khác bản sao

Một số NoSQL áp dụng **anti-entropy**: các replicas so sánh trạng thái/version/hash và truyền những dữ liệu còn thiếu để hội tụ. Hệ có thể dùng Merkle trees, repair jobs hoặc đọc so nhiều replica.

~~~text
Replica A: note-42 tombstone rev=19
Replica B: note-42 live rev=18
Replica C: note-42 tombstone rev=19
~~~

Repair đúng phải đưa B lên **tombstone rev 19**, không coi live rev 18 là một dữ liệu cần hồi phục ở A/C.

Điều kiện:

- Còn tombstone hoặc bằng chứng revision.
- Resolver hiểu thứ tự version và delete semantics.
- Repair không tự ưu tiên “non-null document”.
- Nếu versions concurrent, contract conflict rõ.
- Replica đang offline đủ lâu không được làm giả định tombstone luôn còn.

**Read repair** có thể giúp sửa khi có read chạm dữ liệu, nhưng key ít được đọc vẫn cần kế hoạch background anti-entropy nếu yêu cầu hội tụ hoàn toàn.

## 29. Khi nào có thể dọn tombstone?

Tombstone giúp chặn bản cũ, nhưng lưu vô hạn có thể tốn nhiều dung lượng. **Garbage collection (GC) tombstone** chỉ an toàn khi protocol bảo đảm những nguồn có thể tái xuất hiện bản cũ đã được xử lý hoặc sẽ bị từ chối.

Một số điều kiện ứng viên:

1. Mọi replica/client trong **membership được kiểm soát** đã nhận hoặc thừa nhận delete.
2. Các replica/offline clients chưa xác nhận buộc **full resync** hoặc được từ chối mọi upload từ thế hệ cũ.
3. Không còn message/event cũ chưa xử lý có thể tạo lại record mà thiếu version guard.
4. Backup restore sẽ không đưa dữ liệu cũ vào authoritative state mà bỏ qua delete history.
5. Metadata **min accepted generation/version floor** vẫn được giữ nếu cần.
6. Những giai đoạn retention/compliance đã cho phép purge nội dung và marker theo contract.

**Không có thời hạn TTL cố định nào tự chứng minh an toàn cho mọi hệ**. Một client có thể offline lâu hơn mọi TTL giả định, trừ khi chính protocol đặt giới hạn và buộc client cũ tái đăng ký.

## 30. Chỉ dùng “đã quá 7 ngày” chưa đủ

Ví dụ:

~~~text
Ngày 1: note-42 bị xóa, tombstone rev 19.
Ngày 8: server dọn tombstone vì TTL 7 ngày.
Ngày 30: laptop offline từ ngày 0 kết nối lại.
Laptop push note-42 rev 18.
~~~

Server không còn bản ghi hay tombstone. Nếu nó xử lý **upsert trên miss**, note-42 lại xuất hiện.

Muốn GC sau 7 ngày, phải có một cơ chế:

~~~text
Client sync token có epoch cũ hơn minimumSupportedEpoch
  -> server từ chối incremental push
  -> client phải full resync từ nguồn hiện hành
  -> pending edits được xem xét như conflicts, không tự upsert
~~~

Hoặc server vẫn giữ **compact deletion floor/tombstone identity** đủ lâu để chặn stale IDs. Nếu bất kỳ client cũ nào vẫn được quyền gửi UPSERT không kiểm version, **GC tombstone không an toàn**.

## 31. Min-supported epoch và buộc full resync

Một giao thức có thể duy trì:

~~~yaml
syncProtocolVersion: 4
currentEpoch: 12
minimumAcceptedClientEpoch: 10
latestChangeCursor: 950001
~~~

Thiết bị offline:

~~~text
clientEpoch = 7
~~~

Khi kết nối:

~~~text
POST /sync/push
  clientEpoch=7

Server:
  409 SYNC_EPOCH_TOO_OLD
  requiredAction=FULL_RESYNC
~~~

Những nguyên tắc:

- Server xác minh **epoch của authoritative namespace**.
- Client không tự sửa epoch lên 12 rồi push những writes cũ như hợp lệ.
- Full resync lấy **live dataset + baseline version/cursor** theo snapshot protocol.
- Pending local edits phải được **rebase/giải quyết** dựa trên versions hiện hành.
- Tombstones đã GC không được coi “không có nên CREATE được”.

**Full resync không có nghĩa xóa sạch local user drafts không báo trước**. Cần policy UX, backup local drafts an toàn và bảo vệ quyền riêng tư.

## 32. Full resync phải có snapshot và mốc thay đổi

Nếu client quét dữ liệu sống trong nhiều trang, server có thể tiếp tục nhận UPDATE/DELETE.

Một snapshot protocol đúng:

~~~text
1. Server cấp snapshot token S tại một mốc logic.
2. Client tải các trang nhất quán với snapshot S
   hoặc theo giao thức sync cho phép.
3. Client thay thế/cập nhật local baseline.
4. Client pull change feed kể từ S.
5. Client đánh dấu cursor mới sau khi apply bền vững.
~~~

Nếu không có snapshot xuyên các trang, có thể phát sinh:

~~~text
Page 1 thấy note-42.
Server DELETE note-42.
Page 2 không chứa note-42.
Client kết thúc full sync mà vẫn giữ note-42 từ page 1.
~~~

Một protocol có thể dùng snapshot isolation, consistent snapshot token hoặc bootstrap gồm **copy + change log catch-up**. Không nên tự cho rằng phân trang thông thường tạo snapshot.

## 33. Membership và thiết bị đã bị bỏ quên

Một hệ có thể có:

~~~text
Workspace 7:
  phone-A active
  laptop-B active
  tablet-C offline 18 tháng
~~~

Nếu GC đòi **mọi thiết bị từng tồn tại ACK DELETE**, tablet-C có thể khiến tombstones phải giữ vô hạn.

Các chiến lược:

- Quản lý **registered active devices** và thời hạn được phép offline.
- Thu hồi device/session quá hạn, bắt full resync sau đăng ký lại.
- Dùng **server-authoritative min version floor**.
- Giữ compact tombstone archive lâu hơn payload.
- Thiết kế causal-stability/GC protocol khi membership được quản lý.
- Có **runbook** cho thiết bị mất, hỏng hoặc không còn được tin cậy.

Trong mô hình peer-to-peer hoàn toàn mở, không thể luôn xác định “mọi replica đã nhận DELETE” nếu replica có thể xuất hiện lại sau thời gian không giới hạn. Muốn GC an toàn cần **giả thiết về membership/retention** hoặc thay đổi protocol.

## 34. Cassandra: tombstone, repair và gc_grace_seconds

Apache Cassandra dùng tombstones cho nhiều loại DELETE và TTL. Tombstone giúp các replica không coi giá trị cũ là mới sau khi những replica chưa nhận DELETE trở lại.

Ví dụ:

~~~sql
CREATE TABLE notes_by_id (
    tenant_id text,
    note_id text,
    content text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, note_id))
);

DELETE FROM notes_by_id
WHERE tenant_id = 'shop-a'
  AND note_id = 'note-42';
~~~

Giả sử:

~~~text
Replica A: nhận tombstone
Replica B: nhận tombstone
Replica C: offline, còn live data cũ
~~~

Nếu tombstone bị thu gom trước khi C được repair, dữ liệu cũ ở C có thể gây **resurrection/zombie data** theo cơ chế reconciliation của hệ.

### Vai trò của gc_grace_seconds

**gc_grace_seconds** là một tham số liên quan đến thời gian grace trước khi một số tombstones đủ điều kiện được dọn theo cơ chế compaction. Nó **không tự chạy repair**, cũng không đảm bảo xóa vật lý đúng thời điểm đã định. An toàn phụ thuộc lịch repair, sự vắng mặt của replica, topology, TTL và phiên bản/chiến lược compaction.

Trước khi giảm tham số cần hỏi:

1. Replica nào đã offline lâu hơn repair window?
2. Những DELETE/TTL có thể còn nằm trên một replica cũ không?
3. Repair/anti-entropy đã chạy và hoàn tất đầy đủ trên các ranges liên quan chưa?
4. Có thay node, restore snapshot hoặc rebuild sắp diễn ra không?
5. Có read amplification cao do tombstones và cần tối ưu dữ liệu thay vì chỉ giảm grace?

**Không tùy tiện đặt gc_grace_seconds=0 trên production để dọn nhanh** nếu chưa hiểu điều kiện an toàn của topology/repair trong bản Cassandra cụ thể.

## 35. Cassandra: consistency level không tự giải quyết delete GC

Một ứng dụng dùng:

~~~sql
CONSISTENCY QUORUM;
~~~

trong cqlsh cho một số reads/writes.

Ngay cả khi read/write quorum giao nhau trong giả thiết thích hợp, vẫn phải xét:

- Replica offline đã bỏ lỡ tombstone.
- Hinted handoff chỉ giữ hints theo policy/thời hạn, không thay repair vô hạn.
- Compaction có thể dọn tombstone sau grace.
- Một replica cũ hoặc snapshot restore có thể mang data đã bị xóa.
- Đồng thời writes/TTL có timestamp conflict semantics riêng.

**QUORUM không phải lệnh “đã xóa ở tất cả replica và không bao giờ hồi sinh”.** Muốn bảo vệ delete lâu dài cần replication/repair/GC policy đúng và business-level delete identity nếu client có thể replay.

## 36. CouchDB: revisions, replication và deletion marker

Apache CouchDB là ví dụ quen thuộc của document replication có thể hoạt động khi các phía offline. Documents có **_id**, **_rev** và một deletion marker **_deleted** trong ngữ nghĩa revision/replication.

Một mẫu DELETE đối với revision hiện hành có thể được biểu diễn qua API/document revision theo giao thức CouchDB:

~~~json
{
  "_id": "note-42",
  "_rev": "5-opaque-revision",
  "_deleted": true
}
~~~

Ví dụ ở đây là hình minh họa dữ liệu, không phải lệnh tự tạo một _rev hợp lệ; **revision token do CouchDB cấp theo protocol**, client không tự bịa _rev.

Điểm quan trọng:

- Revision history giúp phát hiện những thay đổi/concurrent branches theo cơ chế replication.
- Xóa document tạo deletion information để truyền tới replicas.
- Replication có thể tiếp tục sau offline và cũng có thể sinh **conflicts**.
- Việc một revision được chọn làm **winning revision** không tự mang ý nghĩa business conflict đã được giải quyết.
- Dọn tombstone hoặc purge có ngữ nghĩa riêng và có thể ảnh hưởng việc các replica cũ đồng bộ trở lại.

Khi client offline đã sửa cùng document, ứng dụng cần đọc/giải quyết conflicts theo policy. **_deleted=true không có nghĩa mọi xung đột và mọi bản copy ở các peers đã được xóa vật lý ngay**.

## 37. CouchDB: delete và purge không phải cùng thao tác

**DELETE** theo document revision giữ thông tin cần cho replication và conflict handling trong phạm vi sản phẩm. **Purge** có ngữ nghĩa loại bỏ revision/data khác, không nên dùng như một cách “giải quyết conflict cho nhanh” nếu còn các replica offline.

Một ví dụ diễn giải:

~~~text
Replica A:
  note-42 -> deleted revision

Replica B (offline):
  note-42 -> live old revision
~~~

Khi replication:

- Hệ cần thông tin deletion revision để xác định trạng thái/nhánh.
- Nếu A đã purge mọi thông tin cần thiết và policy replication không có bằng chứng xóa tương ứng, B có thể vẫn chứa bản cũ.
- Một xung đột live/deleted có thể cần quy tắc ứng dụng về việc hiển thị và giải quyết.

Hãy dùng đúng tài liệu của phiên bản CouchDB cho **deletion, conflict, purge, replication checkpoints**, không giả định purge là một DELETE mạnh hơn nhưng không có hậu quả.

## 38. MongoDB: ứng dụng phải tự thiết kế tombstone nếu cần offline sync

MongoDB replica set sao chép DELETE ở tầng database, nhưng điều đó **không tự thiết kế semantics cho thiết bị offline**.

Nếu app chỉ:

~~~javascript
db.notes.deleteOne({ _id: "note-42" });
~~~

và sau đó chấp nhận:

~~~javascript
db.notes.updateOne(
  { _id: "note-42" },
  { $set: { content: "Bản cũ từ laptop" } },
  { upsert: true }
);
~~~

thì bản cũ có thể được tạo lại.

Một model application-level:

~~~javascript
{
  _id: "note-42",
  tenantId: "shop-a",
  generation: 1,
  revision: NumberLong(18),
  deleted: false,
  content: "Kế hoạch A"
}
~~~

DELETE có điều kiện:

~~~javascript
const result = db.notes.updateOne(
  {
    _id: "note-42",
    tenantId: "shop-a",
    generation: 1,
    revision: NumberLong(18),
    deleted: false
  },
  {
    $set: {
      deleted: true,
      deletedAt: new Date(),
      deleteOperationId: "del-5501"
    },
    $unset: { content: "" },
    $inc: { revision: NumberLong(1) }
  }
);
~~~

Đoạn này minh họa **CAS theo revision trong cùng document**. Cần quản lý type, chỉ số matchedCount, write concern, retry/idempotency và authorization. Nếu record không match, application phải đọc lại trạng thái và áp dụng conflict policy, không tự upsert.

## 39. MongoDB Change Streams: DELETE event cần đường tiêu thụ đáng tin

MongoDB **Change Streams** có thể cung cấp các thay đổi như insert/update/delete theo API hỗ trợ. Consumer có thể lưu **resume token** để tiếp tục từ checkpoint trong phạm vi oplog/change stream được duy trì.

Nhưng:

- Resume token có **cửa sổ khả dụng/điều kiện**; consumer offline quá lâu có thể không resume được.
- DELETE event từ change stream không tự trở thành **tombstone vĩnh viễn trong application data model**.
- Nếu chỉ gửi “documents đang sống” cho mobile, máy offline vẫn có nguy cơ resurrection.
- Nếu consumer dừng lâu hơn log retention, cần **full rebuild/bootstrap** theo protocol.
- Change stream consumer phải áp dụng event và lưu checkpoint bền vững, tránh bỏ sót.
- Với soft delete, event có thể là **update** thay vì delete; downstream phải xem field deleted/version.

Một kiến trúc có thể lưu **tombstones + app change-log** riêng để phục vụ offline clients có thời gian offline dài hơn oplog window. Change Streams có thể được dùng làm tín hiệu ingest vào pipeline, nhưng không nên nhầm **resume token còn hợp lệ** với **cam kết lưu lịch sử xóa vô hạn**.

## 40. DynamoDB: TTL, Global Tables và các bản ghi cũ

DynamoDB có conditional writes trên item và **TTL** để dọn item theo cơ chế dịch vụ. Với một application offline sync, cần phân biệt:

- **Business DELETE** do người dùng thực hiện.
- **TTL expiration** theo chính sách lưu trữ.
- **Conditional write** bảo vệ version/generation.
- **Replication đa vùng** và conflict semantics của Global Tables theo chế độ triển khai.

Ví dụ item ứng dụng:

~~~json
{
  "PK": "NOTE#shop-a#note-42",
  "generation": 1,
  "revision": 18,
  "deleted": false,
  "content": "Kế hoạch A"
}
~~~

Một cách bảo vệ là **UpdateItem với ConditionExpression**:

~~~text
Key:
  PK = NOTE#shop-a#note-42

ConditionExpression:
  #revision = :expectedRevision
  AND #deleted = :false

UpdateExpression:
  SET #deleted = :true,
      #revision = :newRevision,
      #deleteOperationId = :opId
  REMOVE #content
~~~

Đây là mô tả API, không phải object typed AttributeValues hoàn chỉnh. Các conditions và mutation trên **cùng item** là chốt; không làm **GetItem rồi PutItem không điều kiện**.

### Cẩn thận với Global Tables

Nhiều region có thể nhận writes theo ngữ nghĩa cấu hình/chế độ Global Tables. Không được tự suy rằng conditional write thành công ở hai region đang mất WAN vẫn bảo đảm một invariant toàn cục. Trong những chế độ replication có conflict resolution kiểu LWW, **timestamp/order** còn có thể làm một bản cũ hoặc delete được xử lý khác mong đợi nếu data model không có quy tắc chống hồi sinh.

Thiết kế phải theo đúng **consistency mode, replication policy, transaction support và tài liệu dịch vụ** đang dùng. Không gắn công thức quorum hoặc merge policy của một hệ Dynamo-inspired bất kỳ vào mọi chế độ DynamoDB.

## 41. DynamoDB TTL không phải deletion protocol cho thiết bị offline

Giả sử tombstone application có:

~~~text
PK = NOTE#note-42
deleted = true
revision = 19
ttl = now + 7 days
~~~

Khi TTL dọn item, server có thể không còn bản để từ chối **old upsert** từ client. Vì vậy:

- TTL không được ngắn hơn điều kiện safety/retention của protocol.
- Có thể cần **version floor/tombstone archive** độc lập với item nội dung.
- Client cũ phải bị từ chối hoặc full resync khi vượt sync epoch.
- Ghi ở Global Tables/đa vùng cần xét replication delay và những item đang offline ở region khác.
- TTL expiration không phải một **user-requested erasure** hoàn chỉnh tại mọi nơi.

Không sử dụng TTL như thay thế cho **operationId, causal ordering và anti-resurrection check**.

## 42. Redis cache: DELETE nguồn nhưng cache vẫn còn

Ví dụ:

~~~text
MongoDB: note-42 đã tombstone rev=19.
Redis:   cache:note-42 chứa nội dung rev=18.
~~~

Nếu API đọc Redis trước mà không kiểm revision hoặc invalidation, người dùng có thể vẫn thấy dữ liệu đã xóa.

Các chiến lược:

1. **Cache invalidation event** khi DELETE commit.
2. **Versioned cache key**: noteId:generation:revision, lookup current revision theo nguồn.
3. **Cache tombstone** với TTL phù hợp để trả deleted.
4. **Read-through validation** cho dữ liệu nhạy/quyền đã thu hồi.
5. **Fail-closed authorization** thay vì tin cache quyền cũ.

Tuy nhiên, cache delete/invalidation event có thể đến **trước hoặc sau UPDATE cũ**. Nếu cache consumer chỉ chạy SET/DEL không kiểm revision, event cũ có thể tái tạo nội dung:

~~~text
DELETE rev 19 -> DEL cache
UPDATE rev 18 -> SET cache with old data
~~~

Vì vậy cache projection cũng cần **version guard** hoặc một policy invalidation bảo đảm không nhận lại bản cũ.

## 43. Search index: delete cũ và update cũ đến đảo thứ tự

Một hệ search có projection:

~~~text
note-42 rev18 = "Kế hoạch A"
~~~

Event delivery:

~~~text
E19 DELETE rev19
E18 UPDATE rev18 (bị trễ)
~~~

Nếu consumer làm:

~~~text
E19 -> DELETE search document
E18 -> UPSERT search document
~~~

thì search index **hồi sinh** note-42 dù source đã deleted.

Cần giữ hoặc truy vấn một **high-watermark per entity**:

~~~text
searchProjectionRevision[note-42] = 19

On E18:
  if incomingRevision <= projectionRevision:
      ignore
~~~

Nếu không giữ high-watermark sau xóa, cần cách khác như external versioning đúng API engine, tombstone trong projection store hoặc rebuild có consistent snapshot.

Không phải mọi search engine hỗ trợ delete có version precondition cùng semantics. Cần kiểm tra rõ tính **versioned write/delete** của engine được dùng.

## 44. Object storage và attachments

Một note có file đính kèm:

~~~text
note-42
  -> attachment:objects/notes/note-42/photo.jpg
~~~

Xóa note không tự làm object bytes biến mất.

Những câu hỏi:

- Attachment được **sở hữu riêng** bởi note hay nhiều note cùng tham chiếu?
- Có giữ object version/history không?
- Khi DELETE, người dùng còn được tải object bằng URL cũ không?
- Job cleanup có thể chạy sau khi note được tạo lại không?
- Backup/snapshot còn giữ object bao lâu?

Một job xóa cũ nếu chỉ dùng path:

~~~text
DELETE objects/notes/note-42/photo.jpg
~~~

có thể vô tình xóa **attachment mới được tạo lại cùng đường dẫn**. Cần **object generation/version/immutable key**, điều kiện ownership và operation ID, không chỉ một đường dẫn tái sử dụng.

Hệ có thể đánh dấu object để purge sau grace period nhưng **revocation quyền đọc** có thể cần hiệu lực trước khi physical purge hoàn tất.

## 45. Tạo lại có chủ đích và chặn stale client

Giả sử note-42 đã deleted ở generation 1. Người dùng nhấn **Khôi phục** trên thiết bị đang đồng bộ hợp lệ.

Một API riêng:

~~~http
POST /notes/note-42/recreate
Idempotency-Key: restore-2201
~~~

Request:

~~~json
{
  "expectedDeletedGeneration": 1,
  "sourceDraftId": "draft-900"
}
~~~

Server:

1. Xác thực quyền restore.
2. Kiểm note-42 hiện là DELETED và generation đúng.
3. Gán **generation mới** hoặc **ID mới**.
4. Ghi nội dung được phép restore.
5. Phát event CREATE/RECREATE version mới.
6. Lưu operation outcome để retry cùng Idempotency-Key không tạo hai bản.

Một laptop B giữ generation 1 không thể gửi UPSERT thế hệ 1 rồi được server hiểu là recreate. Như vậy **khôi phục có chủ đích** được phân biệt rõ với **resurrection ngoài ý muốn**.

## 46. Backup restore có thể đưa dữ liệu đã xóa quay lại

Timeline:

~~~text
Ngày 01: backup ghi note-42 LIVE revision 18.
Ngày 03: người dùng DELETE note-42, tombstone revision 19.
Ngày 05: hệ thống gặp sự cố.
Ngày 05: operator restore backup ngày 01.
~~~

Sau restore, nếu nguồn phục vụ query trực tiếp từ backup cũ mà không replay deletion log, note-42 có thể sống lại.

Quy trình restore đúng cần:

- Xác định **recovery point objective** và mất dữ liệu cho phép.
- Khôi phục changes/outbox/tombstones sau snapshot đến mốc mục tiêu.
- Không bỏ qua **delete events** hoặc version floors.
- Cảnh báo nếu backup quá cũ so với retention cần thiết.
- Không mở write traffic trước khi hoàn tất bước reconciliation bắt buộc.
- Kiểm tra dữ liệu đã được yêu cầu xóa theo policy vẫn không bị lộ trở lại.

**Backup có thể chứa dữ liệu đã xóa tại nguồn hiện tại**. Cần policy retention, quyền truy cập, purge và test restore phù hợp yêu cầu lưu trữ/quy định.

## 47. Min-version floor để chặn các bản cũ sau restore

Một thiết kế có thể giữ metadata tối thiểu:

~~~text
resourceId: note-42
minimumAcceptedGeneration: 2
minimumAcceptedRevision: 19
~~~

Khi restore một snapshot mang version 18, hệ phải nhận biết rằng snapshot đó **không còn đủ quyền để trở thành authoritative live state**.

Các cách:

- Replay authoritative deletion events sau snapshot.
- Giữ một **protected deletion ledger** có backup/retention riêng.
- Dùng namespace/epoch mới và bắt các clients, projections cùng resync.
- Kiểm tra version floors trước khi cho phép writes/reads.

**Min-version floor cũng cần được bảo vệ khi restore**. Nếu metadata floor bị khôi phục về 0 cùng backup cũ, nó không chặn được gì. Không thể tự tuyên bố an toàn chỉ vì thêm trường floor vào chính dataset có thể rollback.

## 48. Xóa dữ liệu cá nhân và tombstone có mâu thuẫn?

Tombstone giữ bằng chứng xóa, trong khi quyền riêng tư có thể yêu cầu loại bỏ dữ liệu cá nhân không cần thiết.

Một thiết kế hướng giảm dữ liệu:

~~~json
{
  "opaqueObjectKey": "hash-or-internal-id",
  "generation": 1,
  "revision": 19,
  "deleted": true,
  "deleteOperationId": "del-5501"
}
~~~

Tombstone **không cần giữ nội dung note, email, địa chỉ hoặc các trường PII gốc** nếu protocol không yêu cầu. Nhưng một ID hash hoặc token vẫn có thể được xem là dữ liệu cá nhân khi nó liên kết được với một người; phải đánh giá theo ngữ cảnh và quy định áp dụng.

Cần phân biệt:

1. **User-visible deletion:** dữ liệu không còn xuất hiện/tải được.
2. **Logical tombstone:** metadata để ngăn resurrection.
3. **Physical purge:** xóa payload khỏi các stores tương ứng.
4. **Backups/archives:** có retention và kiểm soát truy cập riêng.
5. **Offline devices:** có thể vẫn giữ bản cũ ngoài server đang hoạt động.

Tuyên bố “đã xóa ở toàn bộ hệ thống” chỉ hợp lý sau khi phạm vi và các bước xác minh được định nghĩa.

## 49. Thu hồi quyền với thiết bị offline

Giả sử user-B từng được phép đọc workspace nhưng đã bị thu hồi quyền trong lúc laptop B offline.

Laptop B vẫn còn cached note-42. Khi kết nối:

- B không được tự upload những updates cũ để “khôi phục” quyền hoặc dữ liệu.
- API phải kiểm **quyền hiện hành** trước khi nhận push.
- B không được pull nội dung mới.
- Tùy product policy, client cần xóa/khóa local cache liên quan sau khi nhận thông báo revoke.
- Nếu thiết bị không bao giờ online, server không thể chắc chắn đã xóa được một bản sao vật lý đang nằm trên máy đó.

Vì vậy thiết kế **offline-first** cần tuyên bố rõ threat model: mã hóa local store, key revocation, device enrollment và giới hạn của remote erasure đối với thiết bị mất kết nối.

**Bidirectional sync không được tin rằng client gửi object là bằng chứng client còn quyền sửa object.**

## 50. Schema evolution giữa các phiên bản client

Một thiết bị offline hàng tháng có thể chạy schema cũ:

~~~text
Client v1:
  note fields: id, content, updatedAt

Server v3:
  note fields: id, content, revision, deleted, generation
~~~

Nếu v1 gửi UPSERT không có deleted/version, server có thể hiểu missing fields là giá trị mặc định và xóa tombstone.

Hướng xử lý:

1. Đặt **minimum supported sync protocol version**.
2. Validate bắt buộc baseRevision/generation/operationId ở các operation có mutation.
3. Dùng **explicit patch semantics**, không coi missing field là overwrite toàn document.
4. Migrations phải giữ delete metadata.
5. Cũ quá thì **upgrade/full resync** và rebase local edits.
6. Không âm thầm chuyển **legacy PUT whole object** thành CREATE khi server record missing.

Những trường vận hành như deleted/generation không nên được ghi đè từ payload do client cũ tự đặt nếu server là authority.

## 51. Delta sync và snapshot sync có thể phối hợp

Một kiến trúc thực tế:

~~~text
Client mới đăng ký:
  bootstrap snapshot tại cursor 9000
  sau đó pull changes > 9000

Client hoạt động hằng ngày:
  pull delta từ cursor gần nhất

Client offline 3 tháng, cursor đã expired:
  full resync + conflict review
~~~

Nếu server chỉ giữ change events trong 30 ngày, phải xác định client offline **hơn 30 ngày** làm gì. Không được cho client sử dụng stale cursor rồi tự suy “không có changes” sau khi server không còn lịch sử.

Một response có thể là:

~~~json
{
  "error": "SYNC_CURSOR_EXPIRED",
  "action": "REBASE_REQUIRED",
  "serverEpoch": 12
}
~~~

Client phải thực hiện **đúng rebase protocol**, không chỉ đặt cursor thành latest và giữ nguyên mọi local records cũ.

## 52. Causal stability và lúc nào DELETE không còn bị tranh chấp

Trong các hệ quản lý membership và causal metadata, có khái niệm **causal stability**: một thay đổi có thể được xem là đã biết/được bao hàm bởi tất cả những tác nhân còn được tính trong mô hình, theo protocol cụ thể.

Một khi DELETE đã ổn định về mặt nhân quả và những bản cũ không thể được chấp nhận trở lại, hệ có thể dọn một số metadata cũ.

Nhưng các giả thiết phải rõ:

- Danh sách actors/replicas có giới hạn và được quản lý.
- Offline actor quá hạn sẽ bị loại và buộc resync.
- Old events không thể vượt qua version floor sau khi GC.
- Snapshots và restore không đưa version thấp vào authoritative state.
- State merge bảo đảm không “quên” một DELETE cần thiết.

**Causal stability không tự suy ra từ việc đồng hồ đã trôi qua một tháng**. Nó là property của protocol, membership và acknowledgement.

## 53. Thiết kế một API sync đầy đủ

Một push request:

~~~json
{
  "clientId": "phone-A",
  "clientEpoch": 12,
  "operations": [
    {
      "operationId": "del-5501",
      "objectId": "note-42",
      "generation": 1,
      "baseRevision": 18,
      "type": "DELETE",
      "scope": "workspace-7"
    }
  ]
}
~~~

Một push response:

~~~json
{
  "accepted": [
    {
      "operationId": "del-5501",
      "objectId": "note-42",
      "serverRevision": 19,
      "outcome": "DELETED"
    }
  ],
  "conflicts": [],
  "serverEpoch": 12
}
~~~

Một pull request:

~~~text
GET /sync/changes?cursor=opaque-950000
~~~

Một pull response:

~~~json
{
  "changes": [
    {
      "cursor": "opaque-950001",
      "operationId": "del-5501",
      "objectId": "note-42",
      "revision": 19,
      "generation": 1,
      "deleted": true
    }
  ],
  "nextCursor": "opaque-950001",
  "hasMore": false,
  "serverEpoch": 12
}
~~~

**API contract** phải nói rõ:

- Mutation nào cần expectedRevision/CAS.
- Cách detect và trả conflict.
- Khi nào push được xem là committed.
- Cursor có ổn định qua failover/restore không.
- Event có thể được redeliver không.
- Retention của changelog và tombstones.
- Quy tắc xử lý expired cursor/epoch.
- Ai được CREATE lại một object đã DELETED.

## 54. Pseudocode server: nhận UPDATE và DELETE

~~~typescript
type Operation = {
  operationId: string;
  tenantId: string;
  objectId: string;
  generation: number;
  baseRevision: number;
  type: "UPDATE" | "DELETE" | "RECREATE";
  payload?: unknown;
};

async function applySyncOperation(op: Operation, actor: AuthenticatedActor) {
  assertAuthorized(actor, op.tenantId, op.objectId, op.type);

  // Khái niệm: phải là transaction/conditional operation của database.
  return atomicExecute(async (tx) => {
    const previous = await tx.findOperationResult(
      op.tenantId,
      op.operationId
    );
    if (previous) {
      assertSameRequestFingerprint(previous, op);
      return previous.savedOutcome;
    }

    const current = await tx.readEntityIncludingTombstone(
      op.tenantId,
      op.objectId
    );

    if (op.type !== "RECREATE") {
      if (!current || current.generation !== op.generation) {
        return await tx.saveConflictOutcome(op, "UNKNOWN_OR_STALE_GENERATION");
      }
      if (current.revision !== op.baseRevision) {
        return await tx.saveConflictOutcome(op, "STALE_BASE");
      }
    }

    const next = validateAndBuildNextState(current, op);
    const committed = await tx.conditionallyReplaceEntity(
      current,
      next
    );
    if (!committed) {
      throw new RetryableConcurrencyConflict();
    }

    const change = await tx.appendChangeEvent(next, op.operationId);
    return await tx.saveOperationOutcome(op, change);
  });
}
~~~

Đây là pseudocode. Những hàm transaction, conditional replace, create generation, authorization và version handling phải được triển khai bằng API thực tế của engine. **Không thể chỉ đặt nhiều awaits trong một function rồi coi chúng atomic**.

## 55. Pseudocode client: push rồi pull và không echo

~~~typescript
async function synchronize(client: LocalSyncStore, api: SyncApi) {
  const state = await client.readSyncState();
  const ops = await client.listPendingUserOperations();

  // Operations phải giữ nguyên operationId qua retry.
  const push = await api.push({
    clientEpoch: state.epoch,
    operations: ops
  });

  if (push.requiresFullResync) {
    await client.enterRebaseRequiredState(push.serverEpoch);
    return;
  }

  await client.transaction(async (tx) => {
    for (const outcome of push.accepted) {
      await tx.acknowledgeLocalOperation(outcome);
    }
    for (const conflict of push.conflicts) {
      await tx.saveConflictForReview(conflict);
    }
  });

  let cursor = state.lastCursor;
  while (true) {
    const page = await api.pullChanges(cursor);
    await client.transaction(async (tx) => {
      for (const change of page.changes) {
        // Remote apply KHÔNG sinh local outbox operation mới.
        await tx.applyRemoteChangeByVersion(change);
      }
      await tx.saveLastCursor(page.nextCursor);
      await tx.saveServerEpoch(page.serverEpoch);
    });
    cursor = page.nextCursor;
    if (!page.hasMore) break;
  }
}
~~~

Giới hạn ví dụ:

- Push-before-pull không phù hợp mọi protocol; nếu baseRevision đã stale, server trả conflict và client cần rebase.
- Client phải dùng transaction thật cho remote apply + cursor.
- Local outbox có thể chứa nhiều operations phụ thuộc nhau; không được bỏ qua thứ tự causal.
- Nếu API trả expired cursor giữa chừng, phải chuyển sang full resync.
- Nếu server trả **partial acceptance** cho batch push, chỉ ACK những operations thực sự đã được công nhận.

## 56. Conflict resolution là một business operation

Một tình huống:

~~~text
A DELETE note-42 at v19.
B EDIT note-42 offline from v18.
Server returns CONFLICT_STALE_BASE.
~~~

UI cho người dùng:

~~~text
Ghi chú này đã bị xóa trên thiết bị khác.

Bạn có thể:
  [Bỏ bản chỉnh sửa offline]
  [Lưu nội dung thành ghi chú mới]
~~~

Nếu user chọn **Lưu thành ghi chú mới**:

~~~text
CreateNote(newId=note-99, sourceDraft=local-draft-900)
operationId=create-from-conflict-777
~~~

Đây là một **CREATE mới có chủ đích**, được kiểm quyền và lưu audit. Nó không xóa tombstone v19 của note-42 và không làm client khác nghĩ delete đã bị hủy ngầm.

Trong domain có dữ liệu nhạy cảm, có thể không được cho chọn restore; UX cần tuân thủ policy erasure/ownership.

## 57. Các phép đo cần có khi vận hành

| Metric | Ý nghĩa |
|---|---|
| **sync_push_success_rate** | Bao nhiêu operations được server công nhận? |
| **sync_push_conflict_rate** | Bao nhiêu updates có base version stale/concurrent? |
| **stale_update_rejection_count** | Bao nhiêu writes cũ bị chặn? |
| **delete_propagation_lag** | DELETE mất bao lâu đến các replicas/clients active? |
| **tombstone_count/age** | Dấu xóa đang giữ bao nhiêu và bao lâu? |
| **tombstone_gc_safety_debt** | Có bao nhiêu nguồn chưa xác nhận cần xử lý? |
| **offline_client_age** | Thiết bị active lâu nhất chưa sync là bao nhiêu? |
| **expired_cursor_count** | Bao nhiêu clients phải full resync? |
| **change_feed_backlog** | Consumer nào chưa áp dụng events? |
| **projection_stale_update_ignored** | Update cũ tới sau delete bị bỏ qua bao nhiêu lần? |
| **recreated_object_count** | Có bao nhiêu create-again hợp lệ? |
| **suspected_resurrection_count** | Phát hiện live object có version/generation thấp hơn delete floor |
| **repair_completion_lag** | Anti-entropy/replica repair chưa hội tụ bao lâu? |
| **backup_restore_delete_replay_gap** | Sau restore còn bao nhiêu delete events chưa replay? |
| **data_erasure_backlog** | Những nơi còn chờ xử lý xóa vật lý/quyền đọc |

Không đưa toàn bộ objectId/tenantId vào metric labels có cardinality không kiểm soát. Log/trace chi tiết cần bảo vệ PII và có retention chính sách.

## 58. Một trace giúp điều tra resurrection

~~~text
operationId: stale-edit-900
objectId: note-42
clientId: laptop-B
clientEpoch: 7
baseRevision: 18
incomingGeneration: 1

server:
  currentState: DELETED
  currentRevision: 19
  currentGeneration: 1
  minimumAcceptedEpoch: 10
  decision: REJECT_STALE_EPOCH

after:
  objectState: DELETED
  revision: 19
~~~

Trong một sự cố thật, cần trả lời:

1. DELETE được commit ở đâu và khi nào?
2. Client/device nào có bản copy cũ?
3. Có tombstone/version floor không?
4. Stale update đi qua API nào?
5. Có đường upsert bỏ qua condition không?
6. Một consumer/cache/search projection có bỏ version metadata không?
7. Tombstone đã bị dọn quá sớm?
8. Có restore từ backup hoặc data migration không?

Chỉ quan sát “object xuất hiện trở lại” mà không truy được **source operation + version lineage** rất khó sửa tận gốc.

## 59. Kiểm thử lỗi chủ động

| Lịch thử | Điểm cần quan sát | Kết quả kỳ vọng theo delete-wins contract |
|---|---|---|
| B offline, A DELETE, B online push snapshot cũ | Có stale UPSERT không? | Bị từ chối, note vẫn deleted |
| A DELETE, B EDIT concurrent | Policy có rõ không? | Conflict hoặc delete-wins |
| DELETE response mất, client retry | Có thêm revision/delete event không? | Replay outcome theo operationId |
| Pull DELETE, client crash trước lưu cursor | Có bỏ sót delete không? | Redelivery và apply idempotent |
| Lưu cursor trước apply DELETE | Local còn stale | Test phải phát hiện bug |
| Change events E19 rồi E18 | Consumer có revive projection? | E18 bị ignore |
| Tombstone TTL hết, client cũ quay lại | Có old UPSERT được nhận? | Reject via epoch/floor/full resync |
| Replica offline vượt repair grace | Có zombie data không? | Quarantine/rebuild theo runbook |
| Backup trước DELETE được restore | Delete log có được replay? | Không phục hồi live object sai |
| Client clock nhanh 2 giờ | LWW có ưu tiên stale value? | Không dùng client clock làm authority |
| Recreate hợp lệ generation 2 | Old gen1 edit có được nhận? | Old gen1 bị reject |
| Revoke user rồi client push | Có bypass authorization không? | Reject |
| Projection mất tombstone | Update cũ tới sau DELETE | Không hiện lại object |
| Multi-region partition | Hai nơi ghi/xóa cạnh tranh | Conflict policy, không hứa bảo đảm sai |

Không chạy network partition hoặc restore test trên production khi chưa có kế hoạch, quyền và khả năng rollback. Một lần thử pass không chứng minh mọi lịch lỗi đều an toàn.

## 60. Quy trình xử lý khi phát hiện dữ liệu đã bị xóa hồi sinh

1. **Khoanh vùng:** xác định object ID, tenant, các nơi object đang hiển thị và nguồn dữ liệu có thẩm quyền.
2. **Chặn lan truyền:** ngăn stale clients/consumers tiếp tục upsert trong khi điều tra; không xóa log cần thiết.
3. **Truy lại delete lineage:** operationId, revision, timestamp commit, actor, generation, outbox event.
4. **Tìm đường tái tạo:** old client push, backup restore, delayed event, cache/search projection hay replica repair.
5. **Kiểm tra version guards:** đường nào thiếu CAS, tombstone hoặc floor?
6. **Đánh giá tác động:** ai đã đọc dữ liệu, có vấn đề privacy/security/compliance không?
7. **Sửa state authoritative** bằng một delete/correction operation có ID và version được ghi nhận.
8. **Reconcile các replicas/projections**, không chỉ delete một row đang thấy.
9. **Khôi phục safety mechanism**: retention, epoch, change-feed replay, authorization, schema validation.
10. **Kiểm thử lịch gây lỗi** trên môi trường kiểm soát.
11. **Bổ sung alert** khi incoming version thấp hơn deletion floor nhưng được accept.
12. **Cập nhật runbook/incident record** và xem xét xóa dữ liệu ở backup/third-party theo chính sách.

**Không chữa lỗi resurrection bằng cách thêm một cron DELETE liên tục mà bỏ qua nguồn tạo lại bản cũ**. Cần sửa quy tắc nhận dữ liệu và vòng đời delete metadata.

## 61. Quy trình thiết kế đồng bộ hai chiều chống resurrection

~~~mermaid
flowchart TD
    A["Định nghĩa object ID, generation và quyền"] --> B["Chọn source authority / conflict policy"]
    B --> C["Mỗi mutation có operationId + causal/base version"]
    C --> D["DELETE tạo tombstone/change event có version"]
    D --> E["Push: CAS/conditional merge + dedup"]
    E --> F["Pull: apply events + cursor atomically"]
    F --> G["Consumers: delete và update đều so revision"]
    G --> H["Offline clients: epoch/expired cursor/rebase"]
    H --> I["Tombstone GC chỉ sau safety conditions"]
    I --> J["Backup restore/replay + erasure policy"]
    J --> K["Fault tests, reconciliation và observability"]
~~~

Triển khai theo các bước:

1. **Định nghĩa thao tác xóa:** hide, unlink, archive, delete object hay erasure; scope/authorization.
2. **Chọn ID/generation:** stale UPSERT không được xem là CREATE hợp lệ.
3. **Xác định conflict semantics:** delete-wins, update-wins, manual hoặc CRDT phù hợp.
4. **Dùng causal metadata:** server revisions/CAS hoặc version vectors trong multi-writer.
5. **Ghi tombstone và change event** trong atomic unit/recoverable workflow.
6. **Push idempotent:** mỗi operation có ID ổn định, fingerprint và saved outcome.
7. **Pull có checkpoint bền:** apply changes và cursor cùng transaction hoặc redelivery idempotent.
8. **Chặn echo:** remote applies không tự sinh local operation mới.
9. **Quản lý offline devices:** max offline age, expired cursor, min epoch, full resync/rebase.
10. **Thiết kế lifecycle tombstone:** không GC khi còn đường nhận old writes.
11. **Bảo vệ projections/cache/search:** mọi consumer kiểm revision hoặc giữ high-watermark.
12. **Chuẩn bị restore/repair:** replay delete history, không khôi phục authoritative old bytes.
13. **Xem xét privacy:** payload purge, backups, clients offline, tombstone PII.
14. **Test lịch lỗi** và đo stale rejects, delete propagation và resurrection.

## 62. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách suy luận đúng |
|---|---|---|
| “Không còn row nghĩa là đã xóa vĩnh viễn” | Có thể còn bản cũ offline | Dùng tombstone/version floor |
| “Sync hai chiều = copy toàn bộ record hai bên” | Missing không phân biệt delete | Sync operations/causal metadata |
| “Lấy union tránh mất dữ liệu” | Hồi sinh dữ liệu đã xóa | Theo delete policy |
| “Lấy giao thì an toàn” | Có thể xóa record chưa tải | Snapshot/change log có nghĩa |
| “updatedAt lớn nhất luôn mới” | Clock skew và offline queue | Server revision/causal ordering |
| “Một scalar rev tự client tăng là đủ multi-master” | Hai actor có thể cùng rev | Vector/authority/conflict rules |
| “Vector clock tự quyết định delete thắng” | Chỉ biết causal/concurrent | Define remove-wins/update-wins |
| “CRDT nào cũng remove-wins” | OR-Set có add-wins semantics | Chọn CRDT đúng yêu cầu |
| “Soft delete và physical purge là một” | Tombstone vẫn còn metadata | Phân biệt logical/physical |
| “DELETE không cần nằm trong change feed” | Client offline không biết phải xóa | Truyền delete event |
| “Chỉ cần delete event, không cần version” | Update cũ đến muộn tạo lại projection | High-watermark/version guard |
| “Client apply remote delete rồi push lại là tốt” | Echo/duplicate event | Tách local intent và remote apply |
| “Lưu cursor trước khi apply để nhanh” | Crash bỏ sót delete | Atomic apply+checkpoint |
| “Tombstone TTL 7 ngày luôn an toàn” | Client có thể offline 30 ngày | GC theo safety/epoch |
| “Không còn tombstone thì old upsert hợp lệ” | Có thể đã purge marker | Generation/floor/full resync |
| “Full resync là tải các trang GET thường” | Pages không nhất quán khi có writes | Snapshot + change catch-up |
| “Quorum nghĩa là mọi replica biết delete” | Có replica offline và repair gap | Repair/GC policy |
| “gc_grace_seconds tự chạy Cassandra repair” | Đây là grace/compaction policy | Repair riêng, theo dõi offline |
| “CouchDB purge an toàn hơn delete cho mọi replica” | Có thể mất revision evidence | Hiểu deletion vs purge |
| “MongoDB change stream lưu delete vô hạn” | Oplog/resume window có hạn | App log/tombstone + full resync |
| “TTL DynamoDB là user erasure tức thì” | TTL async và replication có phạm vi | Define deletion lifecycle |
| “Cache DEL là đủ” | Update event cũ có thể SET lại | Versioned invalidation |
| “Search document đã delete không thể trở lại” | Delayed UPDATE có thể upsert | Projection revision floor |
| “Backup restore không ảnh hưởng delete” | Snapshot cũ có live record | Replay delete lineage |
| “Tombstone luôn được giữ payload gốc” | Có thể chỉ cần ID/version tối thiểu | Privacy-aware tombstone |
| “Cùng ID thì restore bản cũ như tạo mới” | Old client có thể giả CREATE | New generation/explicit recreate |
| “Xóa trên server thì xóa được máy offline” | Máy không có kết nối | Threat model/revocation |
| “Hệ hội tụ tức là đúng nghiệp vụ” | Có thể hội tụ về bản resurrected | Business invariants và audit |

## 63. Bài tập thực hành

### Bài tập 1 — Dựng lịch resurrection tối thiểu

Server, điện thoại A và laptop B cùng có note-42 version 5. A DELETE, server xóa vật lý; B offline rồi push bản v5. Hãy vẽ timeline, chỉ ra điều kiện nào khiến bản ghi hồi sinh và cách dùng tombstone version 6 ngăn lỗi.

### Bài tập 2 — Missing hay deleted?

So sánh hai snapshot: A không có note-42, B có note-42. Nêu ít nhất bốn nguyên nhân A không có bản ghi và giải thích vì sao không thể lấy union/intersection một cách mù quáng.

### Bài tập 3 — Thiết kế tombstone

Đề xuất schema tombstone gồm tenantId, objectId, generation, revision, deleteOperationId, deletedAt và trường cần cho sync cursor. Chỉ ra trường nào không cần chứa PII gốc.

### Bài tập 4 — Stale update sau delete

Tombstone note-42 revision 19, client gửi UPDATE dựa trên revision 18. Viết predicate CAS và response conflict để client không tự UPSERT lại.

### Bài tập 5 — Delete concurrent với edit

A và B cùng base revision 18; A DELETE, B EDIT offline. So sánh delete-wins, update-wins và manual conflict, nêu hệ quả UX của từng policy.

### Bài tập 6 — Vector clock

Base {A:2,B:4}. A DELETE thành {A:3,B:4}, B UPDATE thành {A:2,B:5}. Chứng minh chúng concurrent và đề xuất quy tắc business merge.

### Bài tập 7 — Clock skew

DELETE xảy ra 09:00 trên A; B gửi bản v5 nhưng đồng hồ B nhanh 2 giờ. Giải thích vì sao LWW theo client updatedAt có thể hồi sinh bản cũ.

### Bài tập 8 — Generation để tạo lại

note-42 generation 1 đã deleted. Thiết kế explicit RECREATE generation 2 với permission/operation ID. Làm sao từ chối laptop mang generation 1?

### Bài tập 9 — Push idempotency

A gửi DELETE operation del-5501, server commit nhưng HTTP response mất. A retry cùng operationId. Làm sao tránh tạo một revision/delete event mới?

### Bài tập 10 — Pull checkpoint

Client nhận UPDATE E1 và DELETE E2 rồi crash. Xây hai histories: (a) cursor lưu trước E2 khiến bỏ sót DELETE; (b) apply+cursor atomic hoặc replay an toàn.

### Bài tập 11 — Tránh echo

Client pull DELETE từ server rồi local store phát ra outbox DELETE mới. Giải thích vòng lặp và tách user-originated mutation khỏi remote apply.

### Bài tập 12 — Cũ quá phải full resync

Server giữ change feed 30 ngày; laptop offline 90 ngày, vẫn có note-42. Thiết kế SYNC_CURSOR_EXPIRED, bootstrap snapshot và conflict review cho local edits.

### Bài tập 13 — Tombstone GC

DELETE ngày 1, tombstone TTL ngày 8, một thiết bị online ngày 30. Hãy chỉ ra khi nào bản cũ có thể được nhận lại và yêu cầu cần có đối với minimumAcceptedEpoch hoặc version floor.

### Bài tập 14 — Snapshot bootstrap

Client tải full snapshot nhiều trang trong lúc server đang DELETE. Thiết kế snapshot token và change-log catch-up để không giữ record đã bị xóa.

### Bài tập 15 — Membership

Một thiết bị không sync 18 tháng làm tombstone GC bị chặn. Đề xuất active device registry, revoke/expire, full resync và giới hạn của việc xóa bản copy trên thiết bị offline.

### Bài tập 16 — Cassandra repair

RF=3: A/B nhận DELETE, C offline. Tombstone được dọn khi C chưa repair. Trình bày kịch bản zombie data, vai trò gc_grace_seconds và repair runbook.

### Bài tập 17 — CouchDB

Giải thích vai trò _id, _rev, _deleted trong document replication, và tại sao purge không phải cách xử lý conflict mặc định khi còn replicas offline.

### Bài tập 18 — MongoDB CAS

Thiết kế updateOne có filter revision=18, generation=1, deleted=false và mutation tạo tombstone rev19. Vì sao upsert=true không được dùng bừa cho incoming stale edit?

### Bài tập 19 — MongoDB Change Streams

Consumer offline lâu hơn cửa sổ resume token. Đề xuất cách bootstrap lại read model hoặc mobile sync mà không bỏ sót DELETE.

### Bài tập 20 — DynamoDB

Thiết kế UpdateItem với ConditionExpression dựa trên revision, deleted và generation. Giải thích vì sao TTL tombstone không tự chống offline upsert sau thời gian lưu.

### Bài tập 21 — Redis cache

MongoDB đã DELETE note-42 revision 19; Redis còn rev18. Sau invalidation, UPDATE event rev18 đến muộn. Thiết kế versioned cache để không hiển thị lại bản cũ.

### Bài tập 22 — Search projection

Event E19 DELETE được xử lý trước E18 UPDATE. Viết logic consumer dùng high-watermark để bỏ E18, giải thích điều gì xảy ra nếu xóa mất metadata version sau delete.

### Bài tập 23 — Relationship removal

User-B bị bỏ khỏi collaborator list của doc-42, nhưng user_documents index cũ còn record. Vì sao không nên chỉ trông vào index và cần kiểm authorization tại read path?

### Bài tập 24 — Outbox/inbox

DELETE ở nguồn commit nhưng app crash trước khi publish event. Thiết kế transactional outbox và inbox idempotent cho search index, cache và mobile feed.

### Bài tập 25 — Attachment cleanup

note-42 bị xóa, attachment path cũ được tái sử dụng cho generation mới, cleanup job cũ đến muộn. Thiết kế immutable attachment keys/conditional delete để không xóa file mới.

### Bài tập 26 — Backup restore

Backup ngày 1 có note LIVE, ngày 3 DELETE, ngày 5 restore. Viết restore protocol replay delete log/verify revision floor và ràng buộc không để old data phục vụ khi chưa reconcile.

### Bài tập 27 — Erasure và offline clients

Một user yêu cầu xóa dữ liệu cá nhân, nhưng laptop offline còn bản copy. Nêu phần nào hệ chủ có thể kiểm soát, phần nào không thể khẳng định đã xóa tức thì, cùng thiết kế tombstone không giữ payload gốc.

### Bài tập 28 — Schema evolution

Client v1 gửi PUT whole document không có deleted/generation; server v3 yêu cầu baseRevision và operationId. Thiết kế version negotiation để không cho legacy client hồi sinh dữ liệu đã xóa.

### Bài tập 29 — Kiểm thử multi-region

Region A DELETE note-42, Region B đang bị partition và UPDATE cùng note. Thiết kế conflict policy và xác định điều kiện nào khiến không thể đồng thời cam kết mỗi bên luôn ACK và delete-wins tức thời toàn cầu.

### Bài tập 30 — Incident investigation

Một ghi chú bị xóa ngày 3 nhưng xuất hiện trở lại ngày 10. Viết kế hoạch điều tra từ audit log, operationId, tombstone age, offline clients, change feed, cache/search, backup restore tới policy sửa lỗi.

### Bài tập 31 — API sync contract hoàn chỉnh

Thiết kế push/pull endpoint gồm clientEpoch, operationId, baseRevision, generation, tombstone, saved outcome, opaque cursor, expired-cursor error, full resync, authorization và retention.

### Bài tập 32 — Thiết kế hệ thống offline-first

Một sản phẩm quản lý công việc có 500.000 thiết bị, tối đa 90 ngày offline, document edits concurrent, soft delete, relationship removal và compliance erasure. Hãy thiết kế:

1. Nguồn dữ liệu NoSQL có thẩm quyền và data model.
2. Client outbox/inbox và stable operation IDs.
3. Revision/vector/causal metadata và conflict policy.
4. Tombstone schema, deletion propagation và restore-as-new.
5. Change feed/checkpoint và snapshot bootstrap.
6. Chính sách offline 90 ngày, expired cursors và full resync.
7. Tombstone GC có điều kiện, phiên bản/floor khi restore.
8. Search/cache/projection invalidation có version guards.
9. Security/authorization và erasure lifecycle.
10. Fault injection, metrics và incident runbook.

Không thể hoàn thành chỉ bằng câu “DELETE ở database rồi đồng bộ hai chiều”: cần chứng minh **bản dữ liệu cũ không được chấp nhận sau khi đã có quyết định xóa**, kể cả khi thiết bị offline hoặc một consumer đến muộn.

---

**Kết luận:** Đồng bộ hai chiều không phải phép copy những record còn tồn tại giữa hai nơi, mà là **trao đổi các thay đổi có danh tính, phiên bản và quy tắc giải quyết xung đột**. Với thao tác DELETE, sự vắng mặt của dữ liệu không đủ để phân biệt “chưa từng có” với “đã bị xóa”. **Tombstone, delete event và causal/version metadata** giữ bằng chứng để từ chối stale updates, trong khi **operation ID và atomic checkpoint** bảo vệ trước retry, crash và lặp sự kiện. Khi DELETE cạnh tranh với EDIT, ứng dụng phải chọn rõ **delete-wins, update-wins hoặc manual resolution**; không lấy timestamp client hoặc LWW tùy tiện làm sự thật nghiệp vụ. **Garbage collection tombstone chỉ an toàn khi không còn đường hợp lệ để bản cũ được nhận trở lại**, thường đòi quản lý membership, minimum sync epoch, version floor và full resync cho thiết bị offline quá lâu. Các hệ NoSQL như Cassandra, CouchDB, MongoDB và DynamoDB có cơ chế replication/delete khác nhau, còn cache, search index và backup cần được kiểm tra riêng. Thiết kế đúng phải bảo vệ trọn vòng đời **delete → propagate → reconcile → retain/GC → restore/recover**, để một bản cũ được tìm thấy sau nhiều ngày không tự trở thành quyền khôi phục dữ liệu đã xóa.
