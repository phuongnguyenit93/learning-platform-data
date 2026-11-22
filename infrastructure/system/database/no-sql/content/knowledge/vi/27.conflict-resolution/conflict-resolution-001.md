# Nhận diện nhiều phiên bản của cùng dữ liệu trong hệ phân tán

Trong một cơ sở dữ liệu NoSQL phân tán, cùng một bản ghi có thể được lưu ở nhiều node, nhiều vùng địa lý hoặc trên thiết bị người dùng làm việc offline. Khi mọi thay đổi đều được truyền và áp dụng theo cùng một thứ tự, các bản sao cuối cùng có thể biểu diễn một trạng thái giống nhau. Tuy nhiên, **mạng không luôn ổn định, các client có thể ghi đồng thời và việc đồng bộ thường diễn ra bất đồng bộ**. Vì vậy, hai nơi có thể cùng giữ dữ liệu mang một định danh nhưng nội dung và lịch sử cập nhật khác nhau.

Ví dụ, một ứng dụng quản lý hồ sơ khách hàng lưu document:

~~~json
{
  "tenantId": "T-01",
  "customerId": "C-100",
  "email": "an@example.test",
  "phone": "0900000000",
  "status": "ACTIVE"
}
~~~

Trong lúc Region A và Region B mất liên lạc:

- Client ở A sửa `phone` thành `0911111111`.
- Client ở B sửa `email` thành `an.new@example.test`.
- Hai phía có thể trả thành công cục bộ theo write policy của deployment.
- Khi đồng bộ lại, hệ nhìn thấy **hai phiên bản khác nhau của cùng `customerId=C-100`**.

Chúng ta cần trả lời: phiên bản nào kế thừa phiên bản nào, phiên bản nào được tạo độc lập, có thật sự xung đột không, và thông tin nào phải được giữ lại trước khi hòa giải? Nếu chỉ so timestamp hoặc xem bản sao “mới nhất” theo đồng hồ, có thể vô tình làm mất một cập nhật hợp lệ.

Bài học trong chương **Xung đột và đồng bộ** sẽ tập trung vào **nhận diện nhiều phiên bản**: định danh bản ghi và lần thay đổi, xác định quan hệ nhân–quả, dùng revision/ETag, vector clock, version vector, logical clock, causal metadata, lịch sử sự kiện, tombstone và cơ chế đối chiếu giữa replica. Phần giải quyết xung đột (last-write-wins, merge, CRDT hoặc business review) được trình bày như bước tiếp theo, nhưng không được nhầm với bước nhận diện.

> **Phạm vi:** Các thuật ngữ `revision`, `version`, `timestamp`, `etag`, `vector clock`, `sibling`, `conflict`, `MVCC` và `replication sequence` có ý nghĩa cụ thể khác nhau giữa các hệ NoSQL. Ví dụ về các họ Dynamo/Cassandra, CouchDB, MongoDB, DynamoDB, Cosmos DB hoặc offline sync chỉ dùng để minh họa các câu hỏi cần kiểm tra. Không suy từ tên sản phẩm rằng mọi phiên bản/config đều lưu siblings hoặc hỗ trợ cùng causal guarantee.

## 1. “Cùng dữ liệu” được xác định bằng điều gì?

Trước khi so phiên bản, hệ phải xác định **hai giá trị có thuộc cùng một thực thể logic hay không**.

~~~text
Identity:
    (tenantId, entityType, entityId)

Example:
    (T-01, Customer, C-100)
~~~

Một document ở node A và document ở node B có thể cùng ID `C-100`, nhưng nếu tenant khác thì **không** phải cùng thực thể. Ngược lại, một thực thể có thể có các read models và copies với ID vật lý khác nhau.

### 1.1. Ba lớp dễ bị trộn

| Lớp | Ý nghĩa | Ví dụ |
|---|---|---|
| **Logical entity** | Thực thể nghiệp vụ có identity ổn định | Customer C-100 của tenant T-01 |
| **Version** | Một trạng thái/lần thay đổi có metadata nguồn gốc | C-100 ở revision 8 |
| **Replica/copy** | Vị trí lưu bản sao của một version hoặc trạng thái | A, B, C cùng giữ revision 8 |

Ba replicas cùng chứa đúng revision 8 **không có nghĩa có ba phiên bản xung đột**. Chúng chỉ là ba bản sao của một lịch sử.

### 1.2. Identity phải ổn định qua đồng bộ

Một ứng dụng offline tạo bản ghi ở thiết bị bằng UUID ngẫu nhiên, rồi đồng bộ lên server có thể cần giữ một stable `entityId` để mọi thao tác sau trỏ cùng thực thể. Nếu mỗi retry tạo ID mới, hệ có thể nhìn một ý định như nhiều entities khác nhau, không phải “xung đột phiên bản”.

### 1.3. Một entity có thể có nhiều materializations

~~~text
Customer source document
  -> Search index entry
  -> Customer-by-email lookup
  -> Analytics projection
  -> Local offline cache
~~~

Những bản materialized này thường cập nhật trễ. Khác nhau giữa source và search index **không tự là hai concurrent versions** cần merge; có thể chỉ là pipeline lag.

### 1.4. Version scope

Một counter version trên `Customer C-100` khác version của `Order O-200`. `version=8` trên hai thực thể không tạo quan hệ thời gian hay nhân–quả giữa chúng, trừ khi hệ có thêm metadata/giao thức cho phạm vi đó.

## 2. Những nguyên nhân tạo nhiều phiên bản

### 2.1. Ghi đồng thời

Hai client đọc revision 7 và cùng sửa:

~~~text
Client A reads v7 -> writes phone.
Client B reads v7 -> writes email.
~~~

Nếu hệ cho phép cả hai writes mà không có compare-and-set/transaction guard đủ mạnh, có thể tạo hai kết quả với cùng parent revision 7.

### 2.2. Network partition

Region A và B không liên lạc. Mỗi vùng có thể tiếp tục nhận writes theo chế độ multi-writer hoặc local availability. Lịch sử thay đổi tách nhánh.

### 2.3. Replication lag

Node A đã có version mới, node B chưa nhận. Đây có thể là **phiên bản cũ và mới theo quan hệ kế thừa**, không phải hai writes concurrent.

### 2.4. Retry và ACK bị mất

Server đã commit version 8 nhưng client không nhận response; client retry với command ID mới và tạo version 9. Đây là **hai lần áp dụng cùng ý định** nếu idempotency bị thiếu. Cần phân biệt duplicate command với legitimate concurrent update.

### 2.5. Offline-first / thiết bị di động

Hai thiết bị cùng mở bản v7, mất mạng trong một ngày rồi sửa khác nhau. Khi reconnect, server không thể chỉ dùng thời điểm upload để suy ra “thay đổi được tạo sau chắc chắn kế thừa thay đổi trước”.

### 2.6. Thay đổi leader và failover

Một leader cũ có uncommitted writes trong local log; leader mới commit một lịch sử khác. Những bản ghi chưa commit có thể bị rollback theo protocol, không nên nhầm với committed sibling versions được sản phẩm công bố.

### 2.7. Restore hoặc replay cũ

Một worker đọc snapshot v7 rồi replay event cũ sau khi source đã tới v10. Nếu không có version/epoch check, nó có thể ghi đè dữ liệu mới bằng state cũ.

### 2.8. Xóa và tạo lại cùng ID

Một replica thấy tombstone (đã xóa), replica khác giữ document cũ. Nếu thiếu metadata xóa, anti-entropy có thể hồi sinh dữ liệu đã delete. Cùng ID không đủ để xác định “bản nào mới”.

## 3. Một timeline: bản cũ, bản mới, hai nhánh

Khởi đầu:

~~~text
v7 = {name: "An", phone: "0900", email: "old@example.test"}
~~~

Ba tình huống:

**Tình huống A — lag đơn thuần**

~~~text
v7 ----> v8(phone="0911")
          ^
          A đã có v8

B chỉ mới có v7.
~~~

Nếu v8 đã kế thừa v7, chúng có quan hệ có thứ tự; B chỉ cần catch up.

**Tình huống B — concurrent writes**

~~~text
          +----> v8A(phone="0911")
v7 ------|
          +----> v8B(email="new@example.test")
~~~

v8A và v8B có chung ancestor v7 nhưng không thấy thay đổi của nhau. Chúng là **concurrent versions** nếu metadata/giao thức xác nhận quan hệ đó.

**Tình huống C — merge**

~~~text
          +----> v8A ----+
v7 ------|               +----> v9M (merged)
          +----> v8B ----+
~~~

v9M ghi nhận đã xem xét **cả hai nhánh**. Nếu metadata causality của v9M bao trùm v8A và v8B, nó có thể **dominate** các versions ấy.

### 3.1. Hai giá trị khác nhau chưa chắc concurrent

`v7.email=old` và `v8.email=new` có thể là update tuần tự. Đừng bật UI “conflict” cho mọi replica lag.

### 3.2. Hai giá trị giống nhau chưa chắc cùng lịch sử

Hai client độc lập cùng ghi `status=ACTIVE`. Payload bằng nhau nhưng có thể là hai writes concurrent. Điều này quan trọng với audit, idempotency và downstream side effects.

### 3.3. Cùng timestamp chưa chắc cùng version

Độ phân giải milliseconds có thể trùng, clocks có thể lệch. Không dùng `updatedAt` như unique version ID khi cần phân biệt lịch sử.

## 4. Quan hệ nhân–quả: happens-before

Ký hiệu \(a \rightarrow b\) có nghĩa sự kiện \(a\) **happens-before** sự kiện \(b\): có quan hệ nhân–quả hoặc thứ tự được truyền qua giao tiếp. Một cách khái quát:

1. Trong cùng một luồng thực thi tuần tự, sự kiện trước xảy ra trước sự kiện sau.
2. Gửi message xảy ra trước việc nhận chính message đó.
3. Quan hệ có tính bắc cầu: nếu \(a\rightarrow b\) và \(b\rightarrow c\), thì \(a\rightarrow c\).

Nếu **không** có bằng chứng \(a\rightarrow b\) hoặc \(b\rightarrow a\), hai sự kiện có thể được xem là **concurrent** trong mô hình nhân–quả.

### 4.1. Concurrent không nhất thiết cùng mili-giây

Hai writes cách nhau 10 phút theo đồng hồ thực vẫn có thể **không có quan hệ nhân–quả** nếu hai vùng bị partition và không nhìn thấy writes của nhau. “Concurrent” trong causal ordering **không chỉ có nghĩa simultaneous wall-clock time**.

### 4.2. Happens-before khác thứ tự thời gian vật lý

Đồng hồ của A có thể nhanh hơn B 30 giây. B có thể nhận một sự kiện từ A rồi ghi tiếp nhưng timestamp trên B lại nhỏ hơn timestamp A. Vẫn có \(A\rightarrow B\), dù so wall-clock nhìn ngược.

### 4.3. Partial order

Không phải mọi cặp version đều so sánh được về thứ tự nhân–quả:

~~~text
A dominates B      -> A đã biết lịch sử B.
B dominates A      -> B đã biết lịch sử A.
A concurrent B     -> Không nhánh nào bao trùm nhánh kia.
A equal B context  -> Cùng causal context; cần thêm dot/version ID
                       nếu muốn phân biệt các event riêng.
~~~

### 4.4. Vì sao cần causal metadata?

Chỉ nhìn document payload và timestamp không đủ để phân biệt “B chưa đồng bộ v8 của A” với “B đã tự cập nhật từ v7”. Metadata là bằng chứng để tránh tự ý loại một phiên bản hợp lệ.

## 5. Các cách phổ biến để gắn version

| Cách | Thể hiện | Giúp gì? | Không giải quyết |
|---|---|---|---|
| Scalar integer | `version: 8` | OCC trên một owner/luồng tuần tự | Causal concurrency giữa các writers độc lập |
| ETag/revision token | `"etag":"opaque-token"` | Conditional update, cache validation | Quan hệ nhân–quả nếu token chỉ opaque |
| Wall-clock timestamp | `updatedAt` | Hiển thị, retention, LWW nếu policy chọn | Clock skew, concurrent causality |
| Lamport logical clock | `(counter, actor)` | Thứ tự logic tôn trọng happens-before một chiều | Phân biệt concurrency đầy đủ |
| Vector clock | `{A:3,B:2}` | Dominance/concurrency trên actor set | Metadata growth, actor lifecycle |
| Version vector / dotted | Causal context + event dot | Causality với nhiều updates/replicas | Merge semantics của domain |
| Commit log position | `(term,index)` hoặc sequence | Ordering trong một replication group | Cross-group global ordering |
| MVCC transaction ID | Revision/snapshot version | Đọc snapshot và phân biệt versions local | Global causal histories nếu không được thiết kế |
| Event sequence | Stream partition offset | Replay/order theo một stream partition | Thứ tự toàn hệ giữa nhiều partitions |
| Content hash | `sha256(payload)` | Xác minh nội dung/dedupe bytes | Causal order, uniqueness của ý định |

### 5.1. Không có “version metadata tốt nhất” cho mọi hệ

Một API chỉ ghi vào authoritative leader có thể dùng integer version + conditional update. Một ứng dụng multi-master offline có thể cần causal metadata. Một hệ event sourcing có thể dùng per-aggregate sequence và immutable event IDs.

### 5.2. Version ID và causal context là hai chiều

`versionId` xác định một version cụ thể; `causalContext` giúp biết những writes nào version ấy đã nhìn thấy. Một opaque UUID rất tốt để phân biệt hai ghi, nhưng không tự trả lời UUID nào kế thừa UUID nào.

### 5.3. Clock value và revision value là hai thứ khác

`updatedAt` phục vụ báo cáo thời gian; `revision` thường phục vụ kiểm soát cạnh tranh; `eventId` phục vụ dedupe; `vector` phục vụ quan hệ nhân–quả. Không tái sử dụng tùy tiện một field cho mọi trách nhiệm.

## 6. Integer version + optimistic concurrency control

Với một document được ghi qua **một nguồn có thẩm quyền** và API hỗ trợ atomic conditional update:

~~~json
{
  "tenantId": "T-01",
  "customerId": "C-100",
  "version": 7,
  "phone": "0900",
  "email": "old@example.test"
}
~~~

Client A và B đều đọc version 7. A muốn đổi phone, B muốn đổi email.

~~~text
A: UPDATE Customer
   SET phone="0911", version=8
   WHERE id=C-100 AND version=7
   -> SUCCESS

B: UPDATE Customer
   SET email="new@example.test", version=8
   WHERE id=C-100 AND version=7
   -> CONDITION_FAILED
~~~

Nếu condition và update **nguyên tử** trên owner, B không âm thầm ghi đè A. B phải đọc version 8, áp thay đổi mới rồi thử `version=8 -> 9` nếu phù hợp.

### 6.1. Version tăng đơn điệu cần một authority

Hai region tự tăng `version=7 -> 8` khi bị partition có thể cùng tạo **version 8 khác nhau**. Scalar `8` không giải thích nhánh nào thắng hoặc đã bao hàm nhánh nào. Muốn multi-writer phải có cơ chế nhận diện source/causal history phù hợp.

### 6.2. Không dựa vào read–then–write tách rời

~~~text
GET version=7
if version == 7:
    WRITE new document without condition
~~~

Hai clients có thể cùng đi qua nhánh `if`. CAS/conditional write phải được thực thi tại commit boundary.

### 6.3. Khi version mismatch, không mặc định auto-merge

Nếu A đổi phone, B đổi email, merge hai fields có thể hợp lý. Nhưng nếu A `CANCEL Order`, B `CONFIRM Order`, không thể chỉ merge hoặc lấy trạng thái mới nhất mà không xem business transition rules.

### 6.4. OCC giúp ngăn xung đột chứ không phải lưu mọi sibling

Với một authoritative owner, B có thể bị từ chối ngay, nên chỉ một committed branch tồn tại. Một hệ offline/multi-writer có thể **chấp nhận** hai branches và lưu metadata cho reconciliation sau; hai mô hình khác nhau.

## 7. ETag và opaque revision tokens

Một API có thể trả:

~~~http
HTTP/1.1 200 OK
ETag: "cust-C100-rev7"
Content-Type: application/json

{"customerId":"C-100","phone":"0900"}
~~~

Client gửi:

~~~http
PUT /customers/C-100 HTTP/1.1
If-Match: "cust-C100-rev7"
Content-Type: application/json

{"customerId":"C-100","phone":"0911"}
~~~

Server cập nhật nếu ETag còn khớp; nếu đã đổi, có thể trả `412 Precondition Failed` theo API contract.

### 7.1. ETag là token, không phải timestamp

ETag thường nên được xem là **opaque**. Đừng tự parse `"rev7"` để khẳng định causal order hoặc tự tính ETag mới nếu server không công bố định dạng ấy.

### 7.2. ETag không tự là globally unique

Một API có thể tạo ETag theo tài nguyên và representation. Cần đọc scope: token có áp dụng cho base resource, projection, replica, item/partition nào? Không dùng token của search index để update source document.

### 7.3. Có thể dùng `If-None-Match`

Create-if-absent qua HTTP precondition hoặc conditional put giúp ngăn duplicate resource identity khi API hỗ trợ. Nhưng nếu response bị mất sau commit, client phải có stable intent ID để hiểu lần thử sau bị `AlreadyExists` là do chính mình hay writer khác.

### 7.4. ETag và merge

Khi `412`, client có thể fetch representation hiện tại, so với base revision đã đọc rồi quyết định three-way merge. Server sẽ cần CAS mới để commit kết quả merge tránh có writer thứ ba xen vào.

## 8. Lamport clocks: thứ tự logic nhưng chưa đủ nhận diện concurrent

Một **Lamport logical clock** tăng khi có sự kiện nội bộ và điều chỉnh khi nhận message:

~~~text
On local event:
    L = L + 1

On receive message with clock M:
    L = max(L, M) + 1
~~~

Tính chất quan trọng:

\[
a\rightarrow b \implies L(a)<L(b).
\]

Nhưng chiều ngược **không đúng**: \(L(a)<L(b)\) không chứng minh \(a\rightarrow b\). Hai sự kiện độc lập vẫn có thể nhận counter khác nhau.

### 8.1. Total order với tie-breaker

Một hệ có thể sắp theo `(lamportClock, actorId)` để tạo thứ tự tổng trên writes. Đây là một **policy ordering**, không phải bằng chứng rằng event có clock lớn hơn đã nhìn thấy event nhỏ hơn.

### 8.2. Lamport và domain conflicts

Nếu dùng total ordering để chọn một winner, bạn đã quyết định **resolution policy**. Điều đó không tự khiến update bị loại “không tồn tại”; cần cân nhắc audit/history và những writes đã ACK cho client.

### 8.3. Khi nào Lamport hữu ích?

Trong event ordering, causal-aware messaging hoặc systems cần một thứ tự logic rẻ hơn vector clocks. Nhưng để nhận diện cặp writes là concurrent một cách đầy đủ, vector-like causality thường phù hợp hơn.

## 9. Vector clock: biểu diễn lịch sử nhân–quả

**Vector clock** gán một counter cho từng actor/replica tham gia:

~~~json
{
  "A": 3,
  "B": 2,
  "C": 0
}
~~~

Mỗi thành phần mô tả mức lịch sử đã quan sát từ actor tương ứng trong phạm vi vector đang quản lý.

### 9.1. Quy tắc khái niệm

- Khi actor A phát sinh sự kiện mới từ causal context hiện có, tăng thành phần A.
- Khi nhận/merge contexts, lấy **giá trị lớn nhất theo từng actor**.
- So hai vectors bằng quan hệ **component-wise**.
- Actor chưa có trong vector được xem có counter 0 trong một mô hình basic vector clock.

### 9.2. Quan hệ dominance

Với vectors \(x,y\):

\[
x\preceq y \iff \forall i,\ x_i\leq y_i.
\]

Nếu \(x\preceq y\) và tồn tại thành phần nhỏ hơn nghiêm ngặt, \(y\) đã bao hàm causal history của \(x\):

\[
x\prec y.
\]

Nếu không có \(x\preceq y\) cũng không có \(y\preceq x\), ta gọi hai vectors **concurrent/incomparable**.

### 9.3. Ví dụ tuần tự

~~~text
v1 = {A:1, B:0}
v2 = {A:2, B:0}
v3 = {A:2, B:1}

v1 <= v2 <= v3
~~~

v3 đã biết cả updates A:1, A:2 và B:1 theo mô hình.

### 9.4. Ví dụ hai nhánh xung đột

Từ base:

~~~text
base = {A:2, B:1}

A writes:
    x = {A:3, B:1}

B writes concurrently from base:
    y = {A:2, B:2}
~~~

So từng thành phần:

~~~text
x[A]=3 > y[A]=2
x[B]=1 < y[B]=2

Neither x <= y nor y <= x.
=> x and y concurrent.
~~~

Không thể quyết định x/y kế thừa nhau chỉ bằng việc B gửi mutation lên server muộn hơn A một giờ.

### 9.5. Merge causal context

Nếu application đã reconcile x và y, có thể tạo context:

~~~text
join(x,y) = component-wise max
          = {A:3, B:2}
~~~

Nếu actor A phát sinh một sự kiện merge mới, increment A:

~~~text
merged = {A:4, B:2}
~~~

`merged` dominates cả x lẫn y. **Lưu ý:** vector join chỉ merge **causal knowledge**, không tự merge nội dung `phone`/`email` hay bảo vệ domain invariant.

## 10. Một ví dụ đầy đủ: mất liên lạc hai region

Ban đầu Region A và B cùng biết Customer C-100 ở base vector `{A:4,B:3}`.

~~~mermaid
flowchart TD
    BASE["Base v7 context {A:4,B:3}"] --> A["Region A: sửa phone; {A:5,B:3}"]
    BASE --> B["Region B: sửa email; {A:4,B:4}"]
    A --> CHECK{"Causal compare"}
    B --> CHECK
    CHECK --> CONC["Hai versions concurrent"]
    CONC --> MERGE["Domain merge + causal join"]
    MERGE --> M["Merged version context {A:6,B:4}"]
~~~

Tình huống:

~~~text
T0: both regions have base.
T1: network partition.
T2: A accepts phone edit.
T3: B accepts email edit.
T4: network heals.
T5: replicas exchange versions and causal context.
T6: compare => concurrent.
T7: resolver merges fields if permitted by business policy.
T8: merged version records both parents' causal history.
~~~

### 10.1. Vì sao timestamp upload không đủ?

B có thể reconnect sau A nên B version đến server muộn hơn, nhưng B chưa nhìn thấy update phone của A. Arrival time không tạo quan hệ nhân–quả cho thao tác đã thực hiện trước khi nhận message.

### 10.2. Nếu cả hai sửa cùng phone?

Đây là conflict cần policy nghiệp vụ:

~~~text
A: phone = 0911
B: phone = 0922
~~~

Không thể merge bằng cách chép “các fields không đụng nhau”. Có thể yêu cầu user chọn, chọn authoritative source, hoặc dùng LWW nếu mất một update là chấp nhận được. Dù chọn cách nào nên giữ audit/history theo policy.

### 10.3. Nếu A đã nhận B trước khi sửa?

Nếu A merge context B rồi tạo phiên bản mới, vector của nó có thể dominate B. Khi đó B là ancestor, không còn concurrent dù nội dung chưa giống ở một read model do lag.

### 10.4. Nếu không có metadata causal?

Hệ không thể suy chắc quan hệ nhân–quả chỉ từ payload/updatedAt. Có thể coi là potential conflict, dùng server-authoritative CAS hoặc dựa vào version history; không tự kết luận chính xác “A happened after B”.

## 11. Implement quan hệ vector clock trong Java

Ví dụ Java 17+ dưới đây tập trung vào **so sánh causal contexts**. Nó không tự ghi dữ liệu vào NoSQL và không tạo distributed consensus:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public enum CausalRelation {
    EQUAL,
    BEFORE,
    AFTER,
    CONCURRENT
}

public record VectorClock(Map<String, Long> ticks) {
    public VectorClock {
        if (ticks == null) {
            throw new IllegalArgumentException("ticks cannot be null");
        }
        for (var e : ticks.entrySet()) {
            if (e.getKey() == null || e.getKey().isBlank()
                    || e.getValue() == null || e.getValue() < 0) {
                throw new IllegalArgumentException("invalid vector entry");
            }
        }
        ticks = Map.copyOf(ticks);
    }

    public VectorClock increment(String actor) {
        if (actor == null || actor.isBlank()) {
            throw new IllegalArgumentException("actor is required");
        }
        Map<String, Long> next = new HashMap<>(ticks);
        next.put(actor, Math.addExact(next.getOrDefault(actor, 0L), 1L));
        return new VectorClock(next);
    }

    public VectorClock join(VectorClock other) {
        Map<String, Long> result = new HashMap<>(ticks);
        other.ticks.forEach((actor, value) ->
            result.merge(actor, value, Math::max)
        );
        return new VectorClock(result);
    }

    public CausalRelation compare(VectorClock other) {
        Set<String> actors = new HashSet<>(ticks.keySet());
        actors.addAll(other.ticks.keySet());
        boolean less = false;
        boolean greater = false;

        for (String actor : actors) {
            long a = ticks.getOrDefault(actor, 0L);
            long b = other.ticks.getOrDefault(actor, 0L);
            less |= a < b;
            greater |= a > b;
        }

        if (less && greater) return CausalRelation.CONCURRENT;
        if (less) return CausalRelation.BEFORE;
        if (greater) return CausalRelation.AFTER;
        return CausalRelation.EQUAL;
    }
}
~~~

### 11.1. Ví dụ sử dụng

~~~java
VectorClock base = new VectorClock(Map.of("A", 2L, "B", 1L));
VectorClock onA = base.increment("A");
VectorClock onB = base.increment("B");

assert onA.compare(onB) == CausalRelation.CONCURRENT;
assert base.compare(onA) == CausalRelation.BEFORE;

VectorClock merged = onA.join(onB).increment("A");
assert onA.compare(merged) == CausalRelation.BEFORE;
assert onB.compare(merged) == CausalRelation.BEFORE;
~~~

### 11.2. `EQUAL` nghĩa gì?

Hai vectors bằng nhau nghĩa cùng **causal context trong mô hình**. Nó **không tự** chứng minh payload giống nhau hoặc hai writes là một event duy nhất. Cần stable write ID/dot nếu concurrency algorithm có thể tạo nhiều phiên bản với context trùng.

### 11.3. Actor IDs và restart

Không dùng `node-1` kèm counter reset về 0 sau restart nếu có nguy cơ lẫn với lịch sử cũ. Actor identity phải có generation/epoch hoặc counter được lưu bền theo protocol. Đổi IP/node name cũng có ảnh hưởng tới vector metadata.

### 11.4. Số actor tăng vô hạn

Mỗi thiết bị mobile mới một actor thì vector có thể phình tới hàng triệu entries. Trong production cần causal context compaction, stable replica actors, dotted version vectors hoặc một protocol phù hợp; không copy implementation này như giải pháp hoàn chỉnh cho hàng triệu devices.

## 12. Unit tests cho causal relation

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import org.junit.jupiter.api.Test;

class VectorClockTest {
    @Test
    void ancestorAndDescendantAreOrdered() {
        var base = new VectorClock(Map.of("A", 1L, "B", 2L));
        var child = new VectorClock(Map.of("A", 2L, "B", 2L));
        assertEquals(CausalRelation.BEFORE, base.compare(child));
        assertEquals(CausalRelation.AFTER, child.compare(base));
    }

    @Test
    void twoIndependentBranchesAreConcurrent() {
        var x = new VectorClock(Map.of("A", 3L, "B", 1L));
        var y = new VectorClock(Map.of("A", 2L, "B", 2L));
        assertEquals(CausalRelation.CONCURRENT, x.compare(y));
        assertEquals(CausalRelation.CONCURRENT, y.compare(x));
    }

    @Test
    void missingActorMeansZeroInThisModel() {
        var x = new VectorClock(Map.of("A", 1L));
        var y = new VectorClock(Map.of("A", 1L, "B", 1L));
        assertEquals(CausalRelation.BEFORE, x.compare(y));
    }

    @Test
    void joinedAndIncrementedVersionDominatesParents() {
        var a = new VectorClock(Map.of("A", 5L, "B", 3L));
        var b = new VectorClock(Map.of("A", 4L, "B", 4L));
        var merged = a.join(b).increment("A");
        assertEquals(CausalRelation.BEFORE, a.compare(merged));
        assertEquals(CausalRelation.BEFORE, b.compare(merged));
    }

    @Test
    void equalContextsAreEqualInVectorOrder() {
        var x = new VectorClock(Map.of("A", 4L, "B", 2L));
        var y = new VectorClock(Map.of("B", 2L, "A", 4L));
        assertEquals(CausalRelation.EQUAL, x.compare(y));
    }
}
~~~

Các tests chỉ kiểm tra logic so vector trong JVM. Chúng **không chứng minh** hệ replication của database đã lưu vector đúng, không bỏ mất causal context hoặc xử lý actor lifecycle an toàn.

### 12.1. Property-based tests hữu ích

Kiểm tra quan hệ phản xạ, bắc cầu của dominance, symmetry của concurrency và tính chất join dominates parents cho các vectors ngẫu nhiên hợp lệ. Cần tách **logic đại số** khỏi **storage consistency**.

### 12.2. Đồng bộ ở nhiều máy

Một integration test phải mô phỏng hai writers dựa trên cùng base và network partition, sau đó kiểm tra đọc được hai versions hoặc tín hiệu conflict, tùy API. Unit test so vector không đủ.

## 13. Version vector, event dots và dotted version vectors

**Version vector** và **vector clock** thường được dùng gần nhau, nhưng trong các thuật toán lưu nhiều values/siblings, biểu diễn có thể tinh tế hơn. Một vấn đề là cần phân biệt:

- **Causal context**: những writes đã biết.
- **Event mới**: lần write cụ thể vừa phát sinh.

Một dạng khái niệm gọi là **dot**:

~~~text
dot = (actorId, sequenceNumber)

Example:
    (replica-A, 17)
~~~

Một version có thể mang:

~~~json
{
  "versionId": "write-7bb1",
  "dot": {"actor": "A", "sequence": 17},
  "causalContext": {"A": 16, "B": 9},
  "value": {"phone": "0911"}
}
~~~

### 13.1. Vì sao phải có dot?

Giả sử hai writes được tiếp nhận trên cùng server nhưng đại diện hai requests không có quan hệ causal được truyền đúng. Nếu chỉ đánh dấu chung một vector sau merge context, có thể **gộp nhầm** hai sự kiện riêng hoặc không biểu diễn rõ từng sibling. Dot làm rõ identity của event và causal history mà event nhìn thấy.

### 13.2. Dotted version vector không chỉ là “vector cộng thêm field”

Thuật toán thực tế có quy tắc phát dot, join contexts, loại dominated dots, xử lý đồng bộ/retry và garbage collection. JSON trên chỉ là mô hình trực giác, **không** là serialization chuẩn chung hoặc đủ để xây một CRDT/replication engine an toàn.

### 13.3. Siblings

Một hệ có thể giữ nhiều giá trị concurrent cho cùng key:

~~~json
{
  "key": "T-01/Customer/C-100",
  "siblings": [
    {
      "versionId": "va",
      "clock": {"A": 5, "B": 3},
      "value": {"phone": "0911", "email": "old@example.test"}
    },
    {
      "versionId": "vb",
      "clock": {"A": 4, "B": 4},
      "value": {"phone": "0900", "email": "new@example.test"}
    }
  ]
}
~~~

Đây là representation minh họa. Một số sản phẩm lưu conflict revisions, có sản phẩm chỉ trả winner, có sản phẩm merge âm thầm, và có sản phẩm ngăn writes concurrent bằng transaction/CAS.

### 13.4. Version context phải đi cùng update

Nếu client chỉ gửi full document mới mà không gửi base revision/causal token, server có thể không biết update này xuất phát từ bản v7 hay v8. Dùng `If-Match`, revision token hoặc session causal context theo API để giảm blind overwrites.

## 14. Hybrid Logical Clock (HLC) và physical timestamps

Một số hệ sử dụng **Hybrid Logical Clock** kết hợp một phần thời gian vật lý với logical counter để tạo timestamp tôn trọng các quan hệ ordering theo protocol.

Một representation ý tưởng:

~~~text
HLC = (physicalTimeComponent, logicalCounter, nodeId)
~~~

### 14.1. Ưu điểm trực giác

- Có thể gần wall-clock time, thuận tiện debug/tracing.
- Logical component giúp phân biệt events khi thời gian vật lý bằng hoặc đồng hồ có vấn đề.
- Với protocol phát/nhận message phù hợp, có thể giữ property rằng causal predecessor có HLC nhỏ hơn successor.

### 14.2. HLC không tự là vector clock

Một total ordering theo HLC **không chứng minh quan hệ nhân–quả theo chiều ngược**. \(HLC(a)<HLC(b)\) có thể do time/ tie-breaker dù a và b độc lập. Muốn nhận diện concurrency đầy đủ vẫn cần causal context hoặc giao thức với tính chất cụ thể.

### 14.3. Clock skew và giới hạn

HLC có thể giảm một số vấn đề ordering nhưng không loại bỏ mọi giả định về clock. Một system tuyên bố bounded uncertainty/strong external consistency còn cần protocol và clock assumptions riêng. Không suy rằng cứ dùng HLC là mọi read globally linearizable.

### 14.4. Timestamp LWW là policy, không phải detector hoàn hảo

Khi chọn write có timestamp lớn hơn, hệ đang **giải quyết** xung đột theo policy LWW. Metadata timestamp tự nó không thể chứng minh write ấy đã thấy write còn lại.

## 15. Multi-version concurrency control (MVCC)

**MVCC** giữ nhiều phiên bản của dữ liệu để transaction/read có thể quan sát một snapshot và writers không nhất thiết chặn readers theo cùng cách in-place locking.

~~~text
Document C-100:
    committed at version 10: phone=0900
    committed at version 11: phone=0911
    committed at version 12: email=new@example.test

Snapshot at version 10 -> old state.
Snapshot at version 12 -> newer committed state.
~~~

### 15.1. Nhiều MVCC versions không nhất thiết là replication conflict

Hai committed versions được giữ để phục vụ old snapshots có thể nằm trong **một lịch sử có thứ tự**. Không phải cứ engine còn hai physical copies là có hai concurrent siblings.

### 15.2. Snapshot timestamp khác causal vector

Một transaction snapshot ID hữu ích trong phạm vi transaction manager/cluster hỗ trợ. Nó không tự mô tả causal history của các thiết bị offline hoặc multi-region independent writers.

### 15.3. Snapshot isolation vẫn có anomalies

Một transaction đọc consistent snapshot không đồng nghĩa serializable: hai transactions có thể cùng cập nhật các records khác nhau dựa trên invariant chung và gây **write skew**. Cần transaction isolation phù hợp hoặc guard record.

### 15.4. MVCC garbage collection

Các versions cũ có thể được vacuum/compaction sau khi không còn snapshot cần chúng, theo engine. Nếu một client offline cần base revision đã bị GC, hệ phải có strategy full resync/merge hoặc conflict resolution thay vì giả định mọi ancestor được giữ mãi.

## 16. Replication log position, term và stream offsets

Một số systems có thứ tự log:

~~~text
Replication group P:
    term=14
    index=101 -> Update C-100 phone
    index=102 -> Update C-100 email
~~~

### 16.1. Thứ tự trong một group

Trong một consensus replicated log, `(term,index)` hoặc một commit sequence thích hợp có thể giúp xác định thứ tự committed entries của **cùng group**. Nó không tự tạo total order giữa mọi shards/regions nếu hệ không công bố như vậy.

### 16.2. Partitioned event streams

Kafka-like offsets và CDC sequence numbers thường chỉ có thứ tự trong một partition/stream. `offset=300` của partition X không lớn hơn “theo thời gian” `offset=200` của partition Y.

### 16.3. Log sequence và version của document khác nhau

Một log chứa events của nhiều entities. `index=102` có thể cập nhật Customer B chứ không phải Customer C-100. Muốn xác định current version của entity, phải kết hợp logical entity ID và per-entity sequence hoặc source commit metadata.

### 16.4. Failover và uncommitted log

Một old leader có thể có local log entries chưa committed và bị truncate sau election. Đừng nhận diện một entry “đã có trên disk của leader” như một bản hợp lệ đã confirmed cho người dùng nếu contract yêu cầu quorum commit.

## 17. So sánh versions giữa các replica

Một replica trao đổi record:

~~~json
{
  "entityId": "C-100",
  "versionId": "write-A-17",
  "clock": {"A": 17, "B": 8},
  "valueHash": "sha256:<digest>",
  "deleted": false
}
~~~

Replica còn lại có:

~~~json
{
  "entityId": "C-100",
  "versionId": "write-B-9",
  "clock": {"A": 16, "B": 9},
  "valueHash": "sha256:<other-digest>",
  "deleted": false
}
~~~

### 17.1. Quy trình kiểm tra

1. Xác nhận `tenantId/entityId` giống nhau.
2. Kiểm tra version metadata thuộc cùng generation/membership/algorithm.
3. So causal contexts/commit ordering theo contract.
4. Nếu một version dominates version kia, phân loại ancestor/stale.
5. Nếu concurrent, giữ candidates/metadata cho resolver theo policy.
6. Nếu contexts bằng nhưng payload hash khác, điều tra collision/inconsistent metadata/actor identity hoặc thuật toán chấp nhận nhiều event dots.
7. Ghi lại decision cùng provenance và causal context mới nếu merge.

### 17.2. Hash chỉ xác minh nội dung

SHA-256 của payload có thể cho biết hai serialized values giống hay khác nhau (giả định canonical serialization). Nó **không cho biết** version nào causally newer và không thay version clock.

### 17.3. Canonical serialization

JSON object có thể khác thứ tự field, whitespace, số `1` vs `1.0` hoặc Unicode normalization. Muốn dùng hash để đối chiếu bytes về mặt logic, cần canonical encoding đúng schema. Nếu không, cùng dữ liệu có thể cho hash khác dù không có semantic conflict.

### 17.4. Phát hiện conflict không nhất thiết cần tải full payload

Replica có thể trao đổi version metadata/digests trước, sau đó fetch body của các candidates bất đồng. Cách này giảm bandwidth khi phần lớn keys đã đồng bộ.

## 18. Anti-entropy và Merkle trees: tìm key lệch

Khi dữ liệu phân tán lớn, so từng bản ghi ở mọi vòng đồng bộ rất tốn tài nguyên. **Anti-entropy** là nhóm cơ chế trao đổi/đối chiếu để replicas phát hiện và sửa khác biệt.

Một kỹ thuật là **Merkle tree**:

~~~text
               Root hash
              /         \
         hash(L)         hash(R)
         /    \           /   \
       H1      H2        H3     H4
       |       |         |      |
    keys A  keys B     keys C  keys D
~~~

Hai replicas có thể so root hash; nếu khác, đi xuống các branches khác để khoanh vùng key ranges cần trao đổi.

### 18.1. Merkle tree phát hiện khác biệt, không tự quyết định winner

Tree cho biết một range có contents/digests khác nhau. Nó **không** mặc định xác định version nào kế thừa version nào; sau đó vẫn phải trao đổi metadata versions và áp dụng reconciliation policy.

### 18.2. Cần cùng snapshot/range semantics

Nếu một replica xây tree tại thời điểm T1, replica khác tại T2 trong lúc writes tiếp tục, root hashes có thể khác vì dữ liệu đang đổi. Anti-entropy protocols phải có cách xét snapshot/checkpoint/version ranges để tránh kết luận sai hoặc repair vòng lặp.

### 18.3. Partition key/range

Hai replicas chỉ nên so tập key do chúng cùng chịu trách nhiệm theo topology/membership hợp lệ. Nếu rebalancing vừa đổi owners, cần routing/ownership epoch phù hợp để không coi dữ liệu đã chuyển đi là “mất”.

### 18.4. Read repair và background repair

Một read có thể phát hiện replicas trả versions khác và kích hoạt repair; background anti-entropy có thể đồng bộ khi không có read. Cả hai cần hiểu conflicts, tombstones và version metadata để tránh làm mất updates.

### 18.5. Repair không thay durability

Nếu mọi bản sao đã mất một write từng ACK hoặc log cần khôi phục không còn, anti-entropy không tự phát minh lại dữ liệu. Backup/commit guarantees và repair là những lớp trách nhiệm khác nhau.

## 19. Tombstone là một phiên bản có ngữ nghĩa xóa

Trong hệ replicated, `DELETE` thường cần biểu diễn **một sự kiện xóa** chứ không chỉ làm bản ghi biến mất khỏi một node.

~~~json
{
  "tenantId": "T-01",
  "entityId": "C-100",
  "versionId": "delete-B-10",
  "clock": {"A": 17, "B": 10},
  "deleted": true
}
~~~

### 19.1. Rủi ro hồi sinh

~~~text
T0: Replica A, B have Customer C-100.
T1: B deletes C-100; retains tombstone.
T2: A disconnected, still has old live value.
T3: Tombstone removed too early at B.
T4: A reconnects, sends old live value.
T5: System sees value without delete marker -> resurrected.
~~~

### 19.2. Delete cũng có thể concurrent với update

Từ base v7:

~~~text
A updates phone -> v8A.
B deletes entity -> tombstone v8B.
~~~

Nếu hai versions concurrent, câu hỏi “delete wins hay update wins?” là **resolution policy**, không thể quyết định chỉ vì một bản có `deleted=true`. Một hệ có thể dùng remove-wins, add-wins hoặc domain workflow.

### 19.3. Tombstone retention

Đừng GC delete markers trước khi hệ có bằng chứng các replicas/clients liên quan đã nhìn thấy deletion, hoặc trước một retention/sync protocol đủ mạnh. Offline devices kết nối sau nhiều tháng khiến việc xác định safe GC đặc biệt khó.

### 19.4. Business erasure khác logical tombstone

Tombstone giúp ngăn resurrection trong replication, nhưng không tự thực hiện xóa vật lý khỏi mọi backup/index/object store. Với yêu cầu privacy/retention, cần lifecycle policy riêng.

## 20. Xác định conflict trước khi chọn chiến lược xử lý

**Detection** trả lời:

~~~text
Is version A an ancestor of B?
Is version B an ancestor of A?
Are A and B concurrent?
Are these duplicate writes of one command?
~~~

**Resolution** trả lời:

~~~text
If concurrent:
    which value(s) are retained?
    how are fields merged?
    what business invariant must hold?
    who confirms the decision?
    how is the merge version recorded?
~~~

| Resolution policy | Hành vi | Rủi ro |
|---|---|---|
| **Last-write-wins** | Chọn một version theo ordering/timestamp rule | Có thể mất một update đã ACK |
| **Multi-value register** | Giữ nhiều sibling values | Application/user phải giải quyết |
| **Field-level merge** | Merge các field độc lập | Không đúng nếu fields liên quan |
| **CRDT** | Merge operations/states theo đại số phù hợp | Không tự giữ invariant tùy ý |
| **Application/domain merge** | Áp business rules và tạo revision mới | Phức tạp, cần audit/retry |
| **Reject one writer via CAS** | Không cho hai commits concurrent trong scope | Giảm write availability khi cần coordination |

### 20.1. LWW không phải conflict detection

Nếu hệ chỉ giữ winner, application có thể **không thấy sibling** để xử lý. Cần biết API có cung cấp conflict metadata/history hay chỉ giá trị cuối.

### 20.2. Merge fields không được “auto” mọi lúc

Đổi phone và email có thể merge được. Đổi `status=CANCELED` và `charge=CAPTURED` liên quan một state machine có bất biến; ghép cả hai có thể tạo trạng thái không hợp lệ.

### 20.3. Causal join phải đi cùng mutation

Nếu resolver đọc hai branches x/y, tính kết quả, rồi ghi bản mới mà không bao hàm causal contexts của cả hai, hệ có thể tiếp tục báo cùng một conflict sau replication. Merge version phải được ghi kèm metadata/protocol phù hợp.

### 20.4. Resolve cũng có thể bị xung đột

Trong lúc resolver xử lý x/y, writer C có thể tạo z. Commit của merged revision cần compare-and-set/causal validation; nếu không, có thể ghi đè z. “Merge một lần” không tạo quyền độc chiếm vĩnh viễn.

## 21. Event sourcing: phiên bản bằng chuỗi sự kiện

Một hệ lưu events theo aggregate:

~~~json
{
  "aggregateId": "Order-O-100",
  "sequence": 41,
  "eventId": "evt-9d01",
  "type": "OrderConfirmed",
  "commandId": "cmd-6001"
}
~~~

### 21.1. Sequence theo aggregate

Nếu một stream Order chỉ có một authority append với expectedSequence, event 42 phải theo event 41. Hai writers đều đọc `expectedSequence=41`; chỉ một append thành công nếu API enforce condition atomically.

### 21.2. Hai writers độc lập

Nếu offline devices tự gán `sequence=42`, hai events có cùng số nhưng nội dung khác. Cần server authority, stable event IDs hoặc causal/multi-writer protocol; integer sequence cục bộ không giải quyết xung đột.

### 21.3. Idempotency

`eventId` nhận diện event, `commandId` nhận diện ý định của user. Retry một command với eventId mới có thể tạo duplicate business event. Hệ nên có nguyên tắc nhất quán để dedupe khi retry.

### 21.4. Projection lag

Order stream đã có event 42 nhưng read model chỉ replay tới 40. Đây là lag; không xem projection version 40 là một concurrent branch của source event stream.

### 21.5. Snapshot và replay

Snapshot aggregate tại sequence 40 rồi replay 41..42 tạo state mới. Nếu snapshot bị restore sai sequence, replay có thể bỏ sót hoặc lặp effects; cần event ordering, checkpoint và idempotent projection.

## 22. Offline sync: base revision và three-way comparison

Một client offline sửa Profile. Khi reconnect, có ba trạng thái:

~~~text
BASE   = version client đã đọc trước khi offline.
LOCAL  = trạng thái client đã sửa từ BASE.
REMOTE = trạng thái server hiện tại.
~~~

Ví dụ:

~~~json
{
  "base": {
    "version": "r7",
    "name": "An",
    "phone": "0900",
    "email": "old@example.test"
  },
  "local": {
    "baseVersion": "r7",
    "name": "An",
    "phone": "0911",
    "email": "old@example.test"
  },
  "remote": {
    "version": "r8",
    "name": "An",
    "phone": "0900",
    "email": "new@example.test"
  }
}
~~~

### 22.1. Three-way diff

- BASE → LOCAL đổi `phone`.
- BASE → REMOTE đổi `email`.
- Nếu domain policy xác nhận hai fields độc lập, có thể merge hai changes.

### 22.2. Cần base thật, không chỉ latest local

Nếu thiếu BASE, nhìn LOCAL và REMOTE không thể biết một field nào đã bị user chủ động xóa hay chỉ đang cũ. Giữ base revision/diff hoặc đủ context để tái dựng.

### 22.3. Chỉ diff khác nhau chưa đủ causality

Three-way merge hữu ích khi biết LOCAL và REMOTE cùng xuất phát từ base hoặc ancestry đúng. Nếu phiên bản lineage phức tạp, cần revision DAG/causal metadata để tránh merge sai.

### 22.4. Partial patch tốt hơn full replace?

Một PATCH chỉ thay `phone` có thể giảm lost update nếu server enforce đúng semantics, nhưng không tự giữ bất biến chéo fields. Full replacement cần CAS nghiêm hơn để không ghi đè field mà client chưa đọc mới.

### 22.5. Device bị offline quá lâu

Server có thể đã GC base revision, xóa user hoặc thay schema. Client phải full resync, báo conflict hoặc chạy migration, không mặc định mọi local state được merge không mất dữ liệu.

## 23. Cross-region writes và scope của một revision

Một dịch vụ có hai vùng:

~~~text
Region A:
  entity C-100, localRevision=12

Region B:
  entity C-100, localRevision=12
~~~

Hai giá trị `12` không tự nghĩa cùng version. Mỗi vùng có thể tăng counter độc lập.

### 23.1. Định danh có region/actor/generation

Một event identity có thể dùng:

~~~text
(entityId, writerActorId, actorEpoch, actorSequence)
~~~

và causal context riêng. `actorEpoch` ngăn nhầm sequence sau restart/lease change với sequence cũ. Actor identity không thay security principal; writer có thể là replica/coordinator theo protocol.

### 23.2. Causal metadata không sửa được inventory invariant

Hai regions concurrent reserve 8 units từ stock=10, vector clocks có thể **phát hiện** hai nhánh độc lập. Nhưng khi cả hai đã báo `RESERVED`, vector không làm tổng 16 trở về hợp lệ. Muốn giữ invariant phải có authority/quorum, escrow quotas hoặc business compensation rõ.

### 23.3. Session consistency

Một client vừa ghi version x ở Region A muốn read-your-writes ở B. B cần catch up hoặc có session token/causal context theo API. `GET` local ở B trả ancestor có thể đúng eventual contract nhưng không đúng read-your-writes contract.

### 23.4. Global vs local ordering

Một database có strong consistency cho một region/item nhưng cross-region async replication có thể tạo histories khác. Phải ghi phạm vi và topology của `revision`, `timestamp` và commit token; đừng tự so chúng xuyên vùng nếu API không hỗ trợ.

## 24. Read repair có thể vừa phát hiện vừa làm thay đổi state

Một read tới nhiều replicas:

~~~text
Read key K:
    A returns version x
    B returns version y
    C returns version x
~~~

Coordinator so version metadata:

- Nếu x dominates y, có thể coi B lag và thực hiện repair theo protocol.
- Nếu x concurrent y, phải giữ/giải quyết siblings theo policy.
- Nếu x/y same context nhưng payload khác, cần điều tra metadata/protocol corruption hoặc conflict scheme, không tự bỏ qua.

### 24.1. Đọc không nhất thiết chỉ quan sát

Một số hệ kích hoạt read repair/anti-entropy khi read thấy sai lệch; điều đó có thể thêm background writes, IO và latency. Khi đo read SLO phải tính khả năng repair work.

### 24.2. Repair từ một replica “có vẻ mới nhất” là nguy hiểm

Nếu chỉ chọn max `updatedAt` do clocks skew, có thể ghi đè một branch concurrent. Causal metadata giúp phân biệt stale ancestor với independent writer.

### 24.3. Read quorum không tự luôn thấy causal winner

R/W intersection về mặt tập hợp chưa đủ giải quyết concurrent writes, sloppy quorums, conflict resolution và clock assumptions. Phải đọc semantics của hệ hiện hành.

### 24.4. Không so quá nhiều phiên bản trên đường hot read

Nếu một key có hàng nghìn siblings, mỗi GET phải tải/merge tất cả có thể quá chậm. Cần giới hạn versions, resolver workflow, conflict backlog và compaction an toàn.

## 25. Causal metadata và chi phí lưu trữ

Vector clocks cho mỗi record có thể tăng kích thước metadata:

~~~text
10 actor entries x ~20 bytes metadata ~= 200 bytes
1000 actor entries x ~20 bytes metadata ~= 20 KiB
~~~

Đây là ước tính minh họa, không phải kích thước serialization thực tế.

### 25.1. Chi phí của metadata

- Dung lượng document/index/WAL tăng.
- Replication bandwidth tăng.
- So sánh vectors tốn CPU và allocations.
- Clock per-device tăng khi thiết bị mới liên tục xuất hiện.
- Garbage collection và tombstone retention phức tạp.

### 25.2. Actor set có thể được giới hạn

Một số hệ gán actors cho **replication nodes/regions** cố định thay vì mỗi client. Như vậy kích thước vector kiểm soát tốt hơn, nhưng cần protocol để phản ánh writes qua coordinators và tránh “hai writes cùng actor” bị gộp nhầm.

### 25.3. Compaction không được xóa causality cần thiết

Nếu xóa counter của actor A quá sớm, một version cũ từ thiết bị offline có thể trông như mới, gây false conflict hoặc mất dominance. Garbage collection cần evidence rằng history của actor đã được phủ/retired theo protocol.

### 25.4. Metadata schema versioning

Khi đổi từ scalar revision sang vector, không được so `version=10` với `{A:6,B:4}` bằng quy tắc ngẫu nhiên. Cần migration bridge hoặc giữ generation rõ ràng; mixed-mode writers có thể tạo ambiguity.

### 25.5. Khi nào dùng một central authority đơn giản hơn?

Nếu nghiệp vụ phải giữ serializable invariant và khả năng ghi khi partition không phải yêu cầu cứng, single-writer/transaction authority + CAS có thể phù hợp hơn multi-value conflict reconciliation. Đừng triển khai vector clocks chỉ vì NoSQL được gọi là distributed.

## 26. Bảo vệ thông tin version trước các rủi ro bảo mật

### 26.1. Tenant scope

Một khóa version:

~~~text
(tenantId, entityId, versionId)
~~~

phải được xác thực theo tenant. Không cho token hoặc API query version của tenant A truy cập tài liệu tenant B.

### 26.2. Revision token không mặc nhiên là authorization token

Biết ETag/revision ID không phải quyền đọc/ghi. Mọi request vẫn phải đi qua access control và kiểm tra ownership.

### 26.3. Version history có thể chứa dữ liệu đã sửa/xóa

Giữ nhiều revisions cho audit có thể vô tình giữ PII quá hạn. Cần retention/access policy cho history, snapshots, backups và conflict siblings, không chỉ current document.

### 26.4. Hash không che dữ liệu nhạy cảm

Content hash của payload nhỏ/dễ đoán có thể bị dictionary attack hoặc tiết lộ sự trùng khớp. Dùng hash/digest trong logs/telemetry phải xem threat model; không cho rằng SHA-256 tự làm dữ liệu ẩn danh.

### 26.5. Client-supplied clocks không được tin tuyệt đối

Một malicious/offline client có thể gửi vector có counter khổng lồ hoặc timestamp tương lai để “thắng” LWW. Server phải validate causal tokens, actor identity, size bounds và quy tắc cấp counter; không tin metadata ngoài hệ thống như chứng nhận thẩm quyền.

## 27. Observability: biết replica lag hay có conflict thật

| Chỉ số / dấu vết | Câu hỏi |
|---|---|
| Replica apply/commit lag | Bản sao đang cũ tới đâu? |
| Version conflict count | Có bao nhiêu entities có concurrent candidates? |
| Sibling count distribution | Một key có bao nhiêu versions chưa resolve? |
| Conflict resolution latency | Bao lâu thì merge xong? |
| Dropped/LWW-overwritten updates | Có bao nhiêu writes bị policy loại? |
| CAS/ETag mismatch rate | Có hot entity hoặc concurrent edits? |
| CDC lag và sequence gaps | Projection đã bắt kịp source chưa? |
| Anti-entropy backlog | Có bao nhiêu key ranges cần so? |
| Read repair rate | Read thường gặp bản sao lệch không? |
| Tombstone age/GC backlog | Có nguy cơ resurrection không? |
| Offline client age | Bao nhiêu thiết bị dùng base revision rất cũ? |
| Idempotency duplicate attempts | Retry bị nhân đôi hay được dedupe? |
| Actor/vector size p95/p99 | Metadata có tăng vô hạn không? |
| Region conflict rate | Vùng nào tạo nhánh nhiều? |
| Business invariant violations | Merge có tạo trạng thái không hợp lệ? |

### 27.1. Phân biệt conflict từ stale read

Một request đọc từ B thấy v7 khi A đã v8 có thể là normal replication lag. Đếm mỗi stale read thành “conflict” làm cảnh báo giả. Phải kiểm tra **causal relation**, không chỉ `versionId` khác.

### 27.2. Cần gắn đúng scope

Ghi `entityType`, region, bucket/shard, consistency mode, actor generation và source commit/version tokens khi có thể. Hạn chế dùng `entityId` làm metric label cardinality vô hạn; để IDs trong logs/traces có bảo vệ.

### 27.3. Conflict resolution là một workflow

Nếu application cần người dùng xử lý conflict, hãy theo dõi hàng chờ, tuổi của sibling branches, retry/merge failure và business impact. Không chỉ đo số lần conflict được phát hiện.

### 27.4. Không log toàn bộ versions nhạy cảm

Logs nên ưu tiên metadata, safe IDs, hashes phù hợp và diagnostics; payload cá nhân/tài chính cần chính sách bảo vệ.

## 28. Kiểm thử những lịch phân tán dễ gây nhầm

### 28.1. Test stale ancestor

Cho A commit v8 từ v7. Chặn replication tới B để B vẫn giữ v7. Đối chiếu metadata, kỳ vọng v7 là ancestor/stale chứ không là concurrent sibling.

### 28.2. Test hai writers từ cùng base

A và B đọc v7, bị partition rồi tạo hai writes. Theo mode multi-writer, sau heal phải phát hiện concurrent versions hoặc áp một conflict resolution contract đã công bố; không âm thầm khẳng định một update causally superseded update kia.

### 28.3. Test merge lineage

Resolve v8A và v8B thành v9M. Causal context v9M phải bao trùm cả hai theo algorithm; không xuất hiện lại cùng conflict sau anti-entropy nếu không có write mới.

### 28.4. Test equal content, distinct events

Hai writers cùng set `status=ACTIVE` từ một base. Kiểm tra hệ không nhầm hai commands thành một event nếu audit/idempotency semantics cần phân biệt.

### 28.5. Test clock skew

Làm lệch đồng hồ hai region trong môi trường test. Phân tích timestamp LWW có thể chọn version “sai theo ý nghĩa nghiệp vụ” như thế nào; causal relation vẫn được xác định từ metadata được protocol quản lý.

### 28.6. Test delete–update race

Một phía delete record, một phía update dựa trên base cũ. Sau sync, thực thi đúng remove-wins/add-wins/domain policy và kiểm tra không hồi sinh khi tombstone chưa được biết tới.

### 28.7. Test offline client cũ

Một thiết bị giữ base revision 3 tháng, server đã compact lịch sử. Sync phải biết fallback/full refresh/review, không ghi đè current state bằng full document cũ.

### 28.8. Test actor restart

Replica A restart, counter phải không reset một cách gây trùng dot cũ. Nếu actor identity/epoch thay đổi, algorithm phải diễn giải metadata mới đúng.

### 28.9. Test topology change

Khi shard/replica được thêm hoặc di chuyển, không gộp nhầm version vectors khác membership generation; repair không được lấy bản stale ở owner cũ ghi đè owner mới.

### 28.10. Test duplicate command sau ACK loss

Server commit write, drop response, client retry cùng commandId. Kỳ vọng không tạo một mutation business mới; vẫn có thể tạo một transport attempt/log entry tùy implementation, nhưng outcome cuối phải idempotent.

### 28.11. Test snapshot read model

Source ở revision 10, search projection mới xử lý tới revision 8. API phải biết đây là projection lag; không chọn search revision làm winner ngược lên source.

### 28.12. Không chaos-test production bừa

Partition, kill leader, delay replication hoặc sửa clocks chỉ thực hiện trong môi trường được cấp quyền và có dữ liệu test, monitoring cùng cleanup phù hợp.

## 29. Một case study: hồ sơ người dùng từ hai thiết bị offline

**Bối cảnh:** Người dùng mở Profile từ điện thoại và laptop ở version `r7`. Điện thoại sửa số điện thoại khi offline; laptop sửa địa chỉ email khi offline.

### 29.1. Thiết kế naïve

~~~text
On reconnect:
    PUT entire profile.
    Last request to reach server wins.
~~~

Nếu laptop đồng bộ cuối, nó có thể ghi đè phone mới thành phone cũ. Dùng arrival timestamp làm LWW có thể khiến người dùng mất thay đổi không có cảnh báo.

### 29.2. Thiết kế có base revision

Mỗi client gửi:

~~~json
{
  "entityId": "C-100",
  "baseRevision": "r7",
  "commandId": "device-phone-edit-881",
  "patch": [
    {"op": "replace", "path": "/phone", "value": "0911"}
  ]
}
~~~

Server có thể dùng CAS hoặc conflict-aware sync. Nếu một update đã biến state thành r8, server không tự apply full outdated snapshot từ r7; nó xét patch với base/current revisions và các domain rules.

### 29.3. Causal context khi multi-writer thực

Nếu server A và B đều chấp nhận offline writes độc lập, vector clock có thể phân biệt hai branches:

~~~text
phone branch: {A:5,B:3}
email branch: {A:4,B:4}
=> concurrent
~~~

### 29.4. Domain merge

Vì phone/email độc lập theo business assumptions, resolver có thể tạo:

~~~json
{
  "phone": "0911",
  "email": "new@example.test",
  "mergedFrom": ["phone-branch", "email-branch"]
}
~~~

và lưu causal context mới bao trùm hai nhánh, sau đó CAS/commit để tránh ghi đè write thứ ba.

### 29.5. Nếu cả hai sửa cùng email

Không có field-disjoint merge. UX có thể trình bày hai giá trị và yêu cầu chọn hoặc áp policy ưu tiên. Đừng cho rằng “thiết bị đồng bộ cuối” phản ánh ý định cuối của người dùng.

## 30. Case study: giỏ hàng, OR-set và xung đột thao tác

Một Shopping Cart được sửa từ hai thiết bị:

~~~text
Base cart: {A, B}

Phone: add C
Laptop: remove B
~~~

### 30.1. Nếu dùng full-state LWW

Phone gửi `{A,B,C}`; Laptop gửi `{A}`. Nếu Laptop tới sau, C có thể mất. Nếu Phone tới sau, B có thể hồi sinh.

### 30.2. Dùng operation-centric representation

~~~text
Add(C, operationId=op-31)
Remove(B, observedTags=[tag-B1], operationId=op-32)
~~~

Một OR-set/observed-remove set CRDT có thể merge additions/removals theo tags và causal context, tùy semantics add-wins/remove-wins được chọn.

### 30.3. CRDT không tự quản lý tồn kho

Cart có thể hội tụ thành `{A,C}` hợp lệ nhưng sản phẩm C có thể hết hàng. Checkout vẫn cần Inventory authority/conditional reservation để tránh oversell.

### 30.4. Quantity không chỉ là set membership

Số lượng mỗi SKU, remove-all, undo, giá tại checkout và coupon có ngữ nghĩa riêng. Không dùng một CRDT set mẫu cho mọi phần giỏ hàng nếu state transition cần thêm invariants.

### 30.5. Phân biệt commands và versions

Một update Cart có `operationId` để chống duplicate khi retry; state version/causal context để phân biệt lịch sử đồng bộ. Hai metadata khác trách nhiệm dù cùng xuất hiện trong một event envelope.

## 31. Case study: Inventory nhiều region và giới hạn của conflict detection

Tồn kho tổng 10 đơn vị. A và B là hai vùng mất liên lạc:

~~~text
Base stock=10.
Region A confirms reservation of 8.
Region B confirms reservation of 8.
~~~

Vector clocks có thể cho thấy:

~~~text
A reservation branch: {A:4,B:2}
B reservation branch: {A:3,B:3}
=> concurrent
~~~

Nhưng **phát hiện hai branches sau khi đã báo CONFIRMED** không ngăn oversell 16 > 10.

### 31.1. Detect không thay prevent

Những invariants bắt buộc phải giữ ở commit-time cần authority, transaction hoặc protocol phân quyền phù hợp, không chờ đến anti-entropy mới phát hiện sai.

### 31.2. Single authority

Mọi reservation dùng atomic conditional update tại một owner. Khi mất liên lạc, phía không reach owner có thể phải `PENDING` hoặc từ chối. Tradeoff là giảm write availability nhưng bảo vệ invariant.

### 31.3. Escrow quotas

Phân trước 6 units cho A, 4 units cho B; mỗi region chỉ nhận trong quota. Chuyển quota cần protocol không double allocate. Causal metadata vẫn hữu ích cho audit/sync, nhưng quyền phân bổ phải được bảo vệ riêng.

### 31.4. Conflict resolution sau sự cố

Nếu đã oversell, việc chọn một winner bằng LWW không thể xóa nghĩa vụ với khách đã được báo thành công. Cần business compensation, reservation reconciliation và thông báo phù hợp.

## 32. API contract cho version-aware reads và writes

Một API đọc có thể trả:

~~~json
{
  "entityId": "C-100",
  "version": {
    "id": "rev-8a",
    "etag": "opaque-token",
    "causal": {"A": 5, "B": 3}
  },
  "data": {
    "phone": "0911",
    "email": "old@example.test"
  },
  "status": "CURRENT_WITHIN_READ_CONSISTENCY"
}
~~~

Field `status` chỉ là ví dụ **contract tự thiết kế**, không phải một enum có sẵn của NoSQL. Hệ phải ghi rõ `CURRENT` nghĩa current theo source/region/session hay globally linearizable.

### 32.1. Write có expected version

~~~json
{
  "commandId": "update-profile-881",
  "entityId": "C-100",
  "expectedVersionId": "rev-8a",
  "patch": [
    {"op": "replace", "path": "/phone", "value": "0922"}
  ]
}
~~~

Server áp dụng only-if-match tại authoritative commit point hoặc trả conflict có dữ liệu phục vụ re-read. Không coi `expectedVersionId` là quyền truy cập.

### 32.2. Multi-value read

Nếu read API cho phép trả nhiều siblings:

~~~json
{
  "entityId": "C-100",
  "state": "CONFLICT",
  "siblings": [
    {"versionId": "rev-A", "causal": {"A": 5, "B": 3}},
    {"versionId": "rev-B", "causal": {"A": 4, "B": 4}}
  ]
}
~~~

Application cần biết resolver nào chịu trách nhiệm, deadline xử lý và API update sẽ tạo revision bao trùm cả hai contexts như thế nào.

### 32.3. Không để search index tự quyết định bản chính

Một read qua search trả version 7 trong khi source version 8 không có nghĩa source bị conflict. API cần phân biệt `sourceVersion` và `projectionCheckpoint` theo contract nếu mục tiêu là hỗ trợ debugging/sync.

### 32.4. Không lộ toàn bộ causal metadata tùy tiện

Vector clocks có thể chứa node IDs/topology hoặc internal counters. Public API có thể dùng opaque session/revision tokens để tránh phụ thuộc nội bộ; chỉ expose fields cần cho conflict UI khi an toàn.

## 33. Một quy trình nhận diện versions khi đồng bộ

1. **Xác định logical identity.** Bao gồm tenant và loại entity; không lẫn bản ghi khác nhau.
2. **Nhận diện write identity.** Stable `commandId`, `eventId` hoặc dot để phân biệt retry với independent writes.
3. **Kiểm tra source of truth.** Replica, cache, search và CDC projection có scope khác nhau.
4. **Lấy version metadata hợp lệ.** Revision/ETag, causal context, commit sequence, deletion marker và schema generation.
5. **Xác nhận metadata cùng hệ quy chiếu.** Cùng partition/actor membership/clock version hay không?
6. **So quan hệ.** Equal context, ancestor/dominated, descendant hoặc concurrent.
7. **Phân loại stale lag.** Nếu phiên bản cũ là ancestor, có thể chỉ cần catch-up/repair.
8. **Giữ concurrent candidates.** Không xóa loser trước khi resolution policy được thực hiện và lưu dấu.
9. **Phát hiện tombstones.** Delete vs update có thể concurrent và cần quy tắc riêng.
10. **Áp domain resolution nếu cần.** LWW, field merge, CRDT, user decision, reject/conditional retries.
11. **Ghi merged version với causal lineage.** Bao trùm parents và kiểm tra không có write mới xen ngang.
12. **Đồng bộ/repair replicas.** Duy trì idempotency và source authority.
13. **Quan sát backlog và chi phí.** Conflict count, sibling size, lag, tombstone retention.
14. **Kiểm thử failure timelines.** Offline devices, partitions, ACK loss, actor restart, reconfiguration.
15. **Rà soát privacy/retention.** History và conflict copies có thể giữ dữ liệu đã bị xóa.

### 33.1. Ma trận quyết định

| Bản A so với B | Bằng chứng | Hành động cơ sở |
|---|---|---|
| A giống B | Same stable version ID/context và payload theo contract | Không cần merge |
| A là ancestor B | A context được B dominate | Catch up A, không tạo business conflict |
| B là ancestor A | B context được A dominate | Catch up B |
| Concurrent | Neither dominates | Giữ siblings và chạy resolver phù hợp |
| Duplicate command | Cùng stable commandId và payload | Dedupe/return previous outcome |
| Same ID, different payload under same context | Metadata bất nhất hoặc event dots bị thiếu | Điều tra/reject, không arbitrary pick |
| Tombstone vs live ancestor | Tombstone dominates live | Duy trì delete, repair copy cũ |
| Tombstone vs concurrent update | Causal incomparable | Áp remove-wins/add-wins/domain policy |
| Context incompatible generations | Không thể so trực tiếp | Dùng migration bridge/full resync hoặc manual recovery |

## 34. Những sai lầm thường gặp

### “Có ba replicas là có ba versions”

Không. Nhiều copies của cùng một committed revision không phải sibling versions.

### “Hai payload khác nhau nghĩa là hai writes concurrent”

Không. Có thể là ancestor và descendant hoặc projection lag.

### “Hai payload giống nhau nghĩa là cùng một write”

Không. Có thể là hai writes độc lập với cùng value, cần event ID/audit.

### “`updatedAt` lớn hơn luôn causally newer”

Không. Clock skew, offline writes và upload delay có thể đảo thứ tự vật lý.

### “Lamport clock lớn hơn chứng minh đã thấy event nhỏ hơn”

Không. Chỉ có happens-before kéo theo Lamport order theo một chiều.

### “Vector clock tự merge JSON”

Không. Vector chỉ mô tả causal history; domain merge là trách nhiệm khác.

### “Vector clocks bằng nhau là payload chắc chắn giống”

Không nếu metadata được quản lý sai hoặc nhiều event dots không được biểu diễn.

### “Integer version 8 đủ cho mọi multi-region writes”

Không. Hai independent writers có thể cùng tạo scalar version 8.

### “ETag là timestamp có thể parse”

Không nên. ETag thường là opaque token với scope do API quy định.

### “MVCC giữ nhiều versions tức hệ bị conflict”

Không. MVCC có thể giữ lịch sử committed tuần tự phục vụ snapshots.

### “Một CDC offset lớn hơn ở partition A nghĩa mới hơn partition B”

Không. Offsets ở các partitions khác nhau thường không so trực tiếp.

### “Merkle root khác là đã biết winner”

Không. Merkle tree phát hiện khác biệt, không quyết định causal order.

### “Read repair chỉ cần lấy timestamp cao nhất”

Có thể làm mất concurrent update, nhất là khi clocks không đồng bộ.

### “Delete là không còn record nên không cần version”

Sai. Thiếu tombstone/causal delete có thể resurrect dữ liệu cũ.

### “Merge siblings một lần thì conflict sẽ tự hết”

Không nếu merged revision thiếu parents' causal context hoặc writer mới xen ngang.

### “LWW giải quyết xung đột nghĩa là không mất dữ liệu”

Không. LWW có thể bỏ writes đã ACK; cần đánh giá business impact và audit.

### “CRDT nào cũng bảo vệ giới hạn tồn kho”

Không. Convergence không tự đảm bảo quota/invariant có ràng buộc.

### “User offline 6 tháng vẫn luôn merge được với source”

Không. Base history và tombstones có thể bị GC; cần fallback/full resync.

### “Version metadata đưa từ client lên luôn đáng tin”

Không. Client có thể lỗi hoặc cố ý giả counter/timestamp; server phải validate.

### “Chỉ giữ revision hiện tại là luôn đủ”

Không với offline sync/conflict-aware applications; cần chính sách lưu parent/context/deltas phù hợp.

### “Chạy repair là phục hồi được mọi ghi đã ACK”

Không. Nếu dữ liệu không còn trên bất kỳ nguồn bền nào, repair không tự tạo lại.

### “Transaction snapshot đồng nghĩa causal sync toàn region”

Không. Snapshot isolation trong transaction có scope khác multi-region causal history.

## 35. Bài tập thực hành

### Bài 1 — Replica vs version

Ba nodes A/B/C cùng giữ Customer revision r9. B chưa nhận revision r10 của A. Hỏi có bao nhiêu logical versions đang được quan sát? Khi nào đây chỉ là replication lag thay vì conflict?

### Bài 2 — Scalar collision

Hai regions cùng đọc `version=7`, cùng commit local `version=8` khi partition, nhưng payload khác. Vì sao scalar 8 không đủ nhận diện ancestor/concurrent?

### Bài 3 — Compare vectors

Cho \(x=\{A:3,B:1\}\), \(y=\{A:2,B:2\}\), \(z=\{A:4,B:2\}\). Phân loại x/y, x/z, y/z và giải thích từng thành phần.

### Bài 4 — Join contexts

Cho \(a=\{A:5,B:2,C:1\}\), \(b=\{A:4,B:4,C:1\}\). Tính `join(a,b)`; nếu B phát sinh merge event mới, vector tiếp theo là gì? Merge context có tự chọn payload không?

### Bài 5 — Causality và wall clock

Writer A tạo event lúc 10:00 theo máy A; writer B nhìn thấy event A rồi sửa lúc 09:59 theo máy B. Phân tích happens-before và vì sao so timestamp đơn thuần sai.

### Bài 6 — Lamport limitation

Hai event độc lập có Lamport timestamps 5 và 9. Có thể kết luận event 5 happened-before event 9 không? Nếu không, cần metadata nào để xác định concurrency?

### Bài 7 — Optimistic concurrency

Hai clients cùng đọc r7 và update bằng `If-Match:r7`. A success, B 412. Hãy thiết kế re-read + three-way merge + CAS retry, kể cả writer C xuất hiện khi merge.

### Bài 8 — ETag opaque

Một ứng dụng parse ETag để lấy `revisionNumber` rồi tự tăng trước khi PUT. Nêu các assumptions nguy hiểm về scope/format và cách dùng ETag đúng contract.

### Bài 9 — Dotted version vectors

Giải thích sự khác nhau giữa event identity `(actor,seq)` và causal context vector; vì sao chỉ dùng vector context đôi khi không đủ phân biệt hai writes độc lập?

### Bài 10 — MVCC

Database giữ committed revisions 10, 11, 12 để đọc snapshots cũ. Có phải hệ đang giữ ba conflicting siblings? So sánh với hai writes concurrent từ chung revision 10.

### Bài 11 — CDC offsets

Order events ở stream partition P0 có offset 99; Customer events ở P1 có offset 130. Có thể kết luận Customer event mới hơn Order event theo nhân–quả không? Cần thông tin gì?

### Bài 12 — Merkle tree

Hai replicas có root hash khác nhau. Mô tả cách đi xuống tree để tìm key ranges lệch. Tại sao không dùng root hash để chọn winner version?

### Bài 13 — Tombstone resurrection

Replica A offline giữ live Customer r7; B xóa Customer, tombstone bị GC sớm. A quay lại và đồng bộ. Mô tả nguy cơ resurrection, cách giữ/GC delete metadata an toàn theo protocol.

### Bài 14 — Delete vs concurrent update

A update phone từ r7; B delete từ r7. So causal contexts và đề xuất remove-wins, add-wins hoặc business review; mô tả hậu quả mỗi policy.

### Bài 15 — Offline three-way merge

BASE có phone=0900,email=old. LOCAL đổi phone=0911, REMOTE đổi email=new. Hãy tạo merged version. Nếu cả LOCAL và REMOTE đổi phone khác nhau, phải xử lý thế nào?

### Bài 16 — Equal content, distinct commands

Hai clients cùng gửi `status=ACTIVE` với commandIds khác nhau. Payload cuối giống nhau. Khi nào cần lưu hai business events, khi nào có thể dedupe và theo khóa nào?

### Bài 17 — Vector clock actor restart

Replica A đã phát dot `(A,19)`, restart rồi phát lại `(A,1)` vì mất counter. Nêu rủi ro và cách dùng durable sequence hoặc generation/epoch.

### Bài 18 — Memory growth

Một hệ offline có 500.000 thiết bị là potential writers. Vì sao vector một entry/device có thể không thực tế? Đề xuất stable replica actors, context compaction hoặc causal protocol thích hợp.

### Bài 19 — Conflict backlog

Một key có 500 siblings do merge không bao hàm causal lineage. Phân tích vì sao conflict lặp lại sau repair và cách resolver cần ghi context của mọi parents.

### Bài 20 — Clock skew và LWW

Region A đồng hồ nhanh 3 phút, B đồng hồ đúng. A update dựa trên revision cũ nhưng có timestamp lớn hơn. Nếu dùng LWW, update nào có thể mất? Vì sao causal metadata cho phép phát hiện khác biệt?

### Bài 21 — Inventory invariant

Hai regions đồng thời reserve 8 từ stock 10 và vector clock nhận diện conflict. Vì sao detect không ngăn oversell? Thiết kế authority hoặc escrow quotas và quy tắc xác nhận nghiệp vụ.

### Bài 22 — Source vs projection

Order source đã ở version r10 nhưng search index mới phản ánh r8. Làm sao xác định đây là lag, không phải sibling conflict? Những checkpoint/metrics nào cần có?

### Bài 23 — API versioning

Thiết kế `GET` trả ETag/revision và `PATCH` có expectedVersion/commandId. Phân biệt 412, 409, timeout unknown và read-your-writes behavior theo contract.

### Bài 24 — Migration metadata

Hệ chuyển từ integer revisions sang vector clocks. Thiết kế kế hoạch coexistence/mapping, generation IDs và xử lý writers chưa cập nhật để không so sánh hai định dạng một cách tùy tiện.

### Bài 25 — Security

Một client gửi vector counter cực lớn để cố thắng LWW và gửi ETag từ tenant khác. Xác định validation và authorization cần thực hiện, đồng thời bảo vệ version history nhạy cảm.

### Bài 26 — Test harness

Viết mô tả integration test: hai writers từ base giống nhau, partition mạng, ghi hai nhánh, heal, so causal contexts, merge có lineage, chạy anti-entropy và kiểm tra không còn conflict cũ. Phân biệt known ACK với unknown outcome.

---

**Kết luận:** Nhận diện nhiều phiên bản của cùng dữ liệu trong NoSQL phân tán phải bắt đầu từ **logical identity, write identity và phạm vi consistency**, sau đó xác định **quan hệ lịch sử** giữa các versions. Một replica chậm có thể giữ ancestor; hai writers không nhìn thấy nhau có thể tạo **concurrent siblings**; hai payload giống nhau vẫn có thể là hai events riêng; một tombstone cũng là phiên bản có ý nghĩa để tránh hồi sinh dữ liệu. **Scalar revision và ETag** rất hữu ích cho optimistic concurrency tại authority, còn **vector clocks/dotted version vectors** giúp mô hình hóa quan hệ nhân–quả khi có nhiều writers độc lập. Lamport/HLC/timestamp/log offset hỗ trợ ordering ở những phạm vi riêng nhưng **không tự thay thế causal conflict detection**. Anti-entropy, Merkle trees và read repair giúp tìm, đối chiếu và đồng bộ những bản sao khác nhau; bước **resolution** vẫn phải áp đúng quy tắc nghiệp vụ và ghi causal lineage mới. Tách bạch **nhận diện, hòa giải và bảo vệ invariant tại commit** là chìa khóa để không đánh rơi những thay đổi hợp lệ khi hệ thống mất liên lạc rồi đồng bộ trở lại.
