# Thiết kế ca kiểm tra hội tụ và giới hạn của cơ chế giải quyết xung đột

## 1. Bài toán mở đầu: các replica giống nhau nhưng kết quả vẫn sai

Một ứng dụng lưu danh sách sản phẩm yêu thích trên hai vùng địa lý. Người dùng có thể sửa danh sách khi mất mạng, sau đó thiết bị đồng bộ về hệ NoSQL.

~~~text
Ban đầu:
  Region A: favorites = {book}
  Region B: favorites = {book}

Mất kết nối giữa các vùng.

Thiết bị tại A:
  thêm camera
  A: {book, camera}

Thiết bị tại B:
  thêm laptop
  B: {book, laptop}

Kết nối hồi phục.
~~~

Nếu cơ chế giải quyết xung đột chỉ dùng **last-write-wins (LWW)** cho toàn bộ document, tất cả replica cuối cùng có thể cùng mang `{book, laptop}`. Hệ **đã hội tụ** vì hai bên giống nhau, nhưng thao tác thêm `camera` đã bị mất về mặt ý định người dùng.

Một trường hợp nguy hiểm hơn là tồn kho:

~~~text
Ban đầu available=1 tại hai region.

Region A: đọc available=1 -> xác nhận Order A.
Region B: đọc available=1 -> xác nhận Order B.

Sau khi đồng bộ, policy chọn available=0 trên mọi replica.
~~~

Các replica cũng **hội tụ về `available=0`**, nhưng đã xác nhận **hai đơn hàng cho một sản phẩm duy nhất**. Chỉ kiểm tra “các bản sao đã bằng nhau” là chưa đủ.

Bài học này thuộc module **Database No SQL**, chương **Xung đột và đồng bộ**, chủ đề trực tiếp **Thiết kế ca kiểm tra hội tụ và giới hạn của cơ chế giải quyết xung đột**. Mục tiêu là biết viết **kiểm thử có oracle, có mô hình lỗi và có bất biến nghiệp vụ**, không chỉ chờ replication lag về 0 rồi báo thành công.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **conflict detection**, **conflict resolution**, **replication** và **convergence**.
2. Hiểu **eventual convergence**, **strong eventual consistency (SEC)** và các giả định để một kiểm thử có ý nghĩa.
3. Chọn oracle cho **giá trị cuối**, **thứ tự nhân quả**, **bất biến nghiệp vụ** và **độ trễ hội tụ**.
4. Kiểm tra các thuộc tính đại số **giao hoán, kết hợp, lũy đẳng** của merge.
5. Thiết kế test cho **concurrent writes**, offline clients, retry/duplicate, reordered delivery và partition.
6. Kiểm thử LWW, version vector, sibling resolution, custom merge và CRDT theo semantics riêng.
7. Nhận diện **clock skew**, tombstone/TTL, delete resurrection và anti-entropy không bắt kịp.
8. Phân biệt hội tụ của **source data** với cache, search, secondary index hoặc materialized view.
9. Lập ma trận staging/fault injection, telemetry và runbook vận hành.
10. Viết những phép thử Java/JUnit tái hiện kết quả độc lập thứ tự và kiểm chứng bất biến.

---

## 2. Định nghĩa trước khi thử: thế nào là “xung đột”?

Trong hệ phân tán, **xung đột** thường xuất hiện khi nhiều thay đổi tác động tới cùng một logical object trong thời gian chúng chưa có đủ thông tin để xác định hoặc phối hợp một thứ tự có thẩm quyền.

Ví dụ:

~~~text
Replica A: update profile.phone = "090..."
Replica B: update profile.phone = "091..."

Hai thay đổi xảy ra khi A/B không liên lạc được.
~~~

Không phải mọi thay đổi đồng thời đều cần xem là “lỗi”. Có thể chúng:

- Cập nhật những trường khác nhau, cho phép merge.
- Cùng thêm phần tử vào một tập, cho phép union.
- Cùng ghi một giá trị, có thể là idempotent.
- Ghi hai giá trị đối lập, bắt buộc chọn một hoặc giữ cả hai.
- Thực hiện hai hành động hợp lệ riêng nhưng kết hợp lại vi phạm invariant.
- Cập nhật những document khác nhau mà nghiệp vụ lại yêu cầu transaction chung.

### 2.1. Bốn tầng khác nhau

| Tầng | Câu hỏi chính | Ví dụ |
|---|---|---|
| Replication | Thay đổi được vận chuyển đến những replica nào? | A đã gửi delta tới B chưa? |
| Conflict detection | Hệ biết hai thay đổi concurrent hay không? | Version vectors có chỉ ra concurrency? |
| Conflict resolution | Hệ xử lý các thay đổi bất đồng thế nào? | LWW, merge set, app reconciliation |
| Convergence | Cuối cùng các bản sao có về cùng trạng thái không? | A/B/C đều chứa cùng tập giá trị |
| Business correctness | Trạng thái cuối và các side effects có hợp lệ không? | Không bán quá một vé, không thu tiền hai lần |

Một hệ có thể **replicate đủ** nhưng merge sai; có thể **merge đúng kỹ thuật** nhưng business state sai; cũng có thể có final value giống nhau nhưng lịch sử read/write vi phạm yêu cầu consistency mạnh hơn.

### 2.2. “Bản mới nhất” cần định nghĩa rõ

Mới nhất theo:

- Thời gian thực giữa invocation/response?
- Server timestamp?
- Client timestamp?
- Lamport/logical sequence?
- Phiên bản theo một leader?
- Thứ tự nhân quả?
- Quy tắc business (ví dụ trạng thái `CANCELLED` không được tự quay thành `PAID`)?

Các cách này không tương đương. Một test không định nghĩa “mới” theo tiêu chí nào thì khó có oracle đúng.

---

## 3. Convergence, eventual consistency và SEC

### 3.1. Eventual convergence

Trong một mô hình có replication bất đồng bộ, nếu các update liên quan được truyền đến đầy đủ, hệ ngừng nhận update mới và có đủ thời gian/khả năng đồng bộ, những replica trong cùng phạm vi có thể dần đạt trạng thái tương đương.

Nói “eventually” không có nghĩa “trong đúng 100 ms”. Cần phân biệt một **bảo đảm lý thuyết theo giả định** với **SLO thời gian hội tụ đo được**.

### 3.2. Strong eventual consistency (SEC)

Trong những mô hình SEC thường được dùng khi bàn về CRDT, một thuộc tính quan trọng là: **các replica đã nhận cùng một tập các update hợp lệ thì có trạng thái tương đương**, ngay cả khi thứ tự nhận update khác nhau, trong những giả định của thuật toán.

Không nên khẳng định mọi NoSQL eventual-consistent đều có SEC. Một chính sách LWW dựa vào clock, một implementation custom merge không deterministic hoặc một pipeline xử lý duplicate không đúng có thể không thỏa những tính chất đó.

### 3.3. Trạng thái bằng nhau không phải thuật ngữ duy nhất

Hai replica có thể khác metadata nội bộ nhưng quan sát tương đương:

~~~text
Replica A:
  value = {book, camera}
  metadata: vector/version history X

Replica B:
  value = {book, camera}
  metadata: compacted history Y
~~~

Tùy contract, test có thể so:

1. **User-visible values** đã canonicalize.
2. **Logical state** gồm tombstone/version để bảo đảm tương lai không phân kỳ.
3. **Quorum/committed history** trong hệ leader-based.
4. **Downstream read models** theo watermark riêng.

**Chỉ so JSON payload có thể bỏ qua sự khác biệt về tombstone/version khiến lỗi xuất hiện về sau.**

### 3.4. Giới hạn giả định

Khi còn:

- Partition không bao giờ lành.
- Replica không đủ nguồn dữ liệu sau log expiration.
- Stream bị mất event.
- Node cũ ghi đè state không hợp lệ.
- Tombstone bị GC quá sớm.
- Update mới liên tục mà test không có mốc hội tụ.

thì một phát biểu “mọi replica sẽ hội tụ trong thời gian hữu hạn” cần được xem xét lại. Test phải ghi rõ khi nào **ngừng phát sinh update**, mạng đã phục hồi và các điều kiện đồng bộ thực sự được đáp ứng.

---

## 4. Định nghĩa oracle: test cần trả lời điều gì?

Một ca kiểm thử tốt không chỉ có input và sleep, mà có:

- **Setup:** trạng thái ban đầu, schema, topology, replica membership.
- **History:** các operations cùng thời điểm gọi/trả kết quả.
- **Fault schedule:** mạng, crash, delay, reorder, duplicate.
- **Resolution policy:** quy tắc quyết định trạng thái cuối.
- **Convergence trigger:** network heal, anti-entropy/repair theo engine.
- **Oracle:** tiêu chí đạt/không đạt.
- **Observation points:** key/replica/region, read mode và timestamp/watermark.
- **Timeout:** giới hạn đợi của test, tách với bảo đảm lý thuyết.
- **Cleanup:** bảo đảm môi trường không còn trạng thái lỗi ảnh hưởng test sau.

### 4.1. Ba nhóm oracle độc lập

| Oracle | Ví dụ assert | Giới hạn |
|---|---|---|
| **Hội tụ** | Mọi replica trả cùng logical value sau repair | Không chứng minh value hợp nghiệp vụ |
| **Bảo toàn ý định** | Hai concurrent adds của user đều có mặt | Không phải policy nào cũng bảo toàn cả hai |
| **Invariant nghiệp vụ** | Tổng confirmed seats không vượt capacity | Merge tổng hợp có thể vẫn hội tụ nhưng đã oversell |

### 4.2. Thêm oracle thời gian

Ví dụ một SLO được thiết kế:

~~~text
Khi liên kết A-B hồi phục và không có update mới,
99% các key thuộc tập kiểm tra hội tụ trong 30 giây.
~~~

Đây là **mục tiêu đo của hệ**, không phải đặc tính chung của NoSQL. Cần chỉ rõ sample, thời điểm bắt đầu đo, cách nhận biết “đã hồi phục” và đường đọc nào được kiểm.

### 4.3. Không dùng `sleep(5000)` làm oracle

Sai:

~~~java
Thread.sleep(5000);
assertEquals(readRegionA(key), readRegionB(key));
~~~

Nếu cluster chậm do compaction, test có thể fail giả. Nếu cluster chỉ tình cờ đồng bộ ở giây thứ 5 nhưng metadata xóa không đúng, test có thể pass giả.

Tốt hơn:

- Poll các điểm quan sát cho tới deadline.
- Ghi latency/thời gian hội tụ.
- Chỉ kết luận từ trạng thái và policy cụ thể.
- Giữ lịch sử thao tác để chẩn đoán.
- Tiếp tục kiểm thêm sau GC/restart/repair trong những ca phù hợp.

---

## 5. Lập mô hình xung đột bằng quan hệ nhân quả

Hai thao tác A và B có thể:

- A xảy ra trước B theo **happens-before**.
- B xảy ra trước A.
- A và B **concurrent** khi không có thứ tự nhân quả giữa chúng theo mô hình.

~~~text
Client 1:
  write x=v1 -> ACK
  then write x=v2

Client 2:
  offline write x=v3
  without seeing v2
~~~

Tùy context/version metadata, hai write `v2` và `v3` có thể concurrent. **Không tự gán thứ tự thời gian thực từ timestamp thiết bị offline.**

### 5.1. Lamport clocks

Lamport clock giúp biểu diễn một thứ tự hợp lệ với một số tính chất nhân quả. Nhưng:

\[
A\rightarrow B\implies L(A)<L(B)
\]

không có chiều đảo nói rằng \(L(A)<L(B)\) chứng minh A gây ra B. Hai event concurrent vẫn có thể được gán một total order giả tạo.

### 5.2. Version vectors

Version vector có thể biểu diễn những update đã quan sát theo từng actor/replica.

Ví dụ:

~~~text
V1 = {A:2, B:0}
V2 = {A:1, B:1}
~~~

Nếu một vector không nhỏ hơn hoặc bằng vector kia theo từng thành phần, chúng không thể sắp thành quan hệ “đã bao hàm” đơn giản; đó là một dấu hiệu concurrency trong mô hình version vector tương ứng.

### 5.3. Cần test metadata, không chỉ value

Hai update có cùng nội dung string `"ACTIVE"` nhưng khác causal context vẫn có thể quan trọng khi một update được dùng để thay thế/delete theo version history. Nếu test chỉ so string, nó có thể bỏ qua lỗi phát hiện concurrency.

### 5.4. Vector metadata cũng có giới hạn

Version vectors có thể lớn theo số writer/replica và cần xử lý actor churn, pruning, recovery, compaction. Không coi một vector tùy ý kích thước cố định là đủ cho mọi lịch sử vô hạn.

---

## 6. Bộ thuộc tính đại số cho merge dạng state-based CRDT

Một cách thiết kế hội tụ là cho state có phép **join/merge** tuân những tính chất thích hợp trong một join-semilattice.

Với trạng thái \(a,b,c\), ta kỳ vọng:

### 6.1. Giao hoán — Commutativity

\[
merge(a,b)=merge(b,a).
\]

**Ý nghĩa kiểm thử:** đổi thứ tự nhận state A và B không làm thay đổi kết quả logic.

### 6.2. Kết hợp — Associativity

\[
merge(merge(a,b),c)
=
merge(a,merge(b,c)).
\]

**Ý nghĩa:** gộp theo cây, batch hoặc topology khác nhau cho kết quả tương đương.

### 6.3. Lũy đẳng — Idempotence

\[
merge(a,a)=a.
\]

**Ý nghĩa:** duplicate delivery/replay của cùng state không tăng hiệu ứng một lần nữa.

### 6.4. Tính tăng đơn điệu theo partial order

Với mô hình join-semilattice phù hợp:

\[
a\le merge(a,b),\quad
b\le merge(a,b).
\]

State tiến tới trạng thái bao hàm thông tin trước đó theo partial order **của mô hình CRDT**, không nhất thiết một số counter hay timestamp luôn tăng theo thứ tự số học.

### 6.5. Identity khi có

Một số cấu trúc có trạng thái rỗng \(e\):

\[
merge(a,e)=merge(e,a)=a.
\]

### 6.6. Những tính chất này chưa chứng minh business invariant

Một G-Counter CRDT hội tụ dù các client dùng nó sai để biểu diễn **số ghế còn lại** bằng cách cộng dồn bán vé độc lập. CRDT có thể giữ mọi increment đúng nhưng làm tổng bán vượt capacity.

**Merge đúng đại số là một tầng; quyền cấp phát, uniqueness và transaction invariant là tầng khác.**

### 6.7. Operation-based CRDT có điều kiện khác

Với op-based CRDT, delivery assumptions, deduplication, causal ordering hoặc tính giao hoán của concurrent operations có thể đóng vai trò khác state-based merge. Không áp bộ kiểm thử state merge y nguyên cho mọi operation stream mà không xem giao thức.

---

## 7. Ví dụ đơn giản: Last-Write-Wins và giới hạn

Một LWW register thường giữ một cặp:

~~~text
(timestamp-or-version, value)
~~~

Merge chọn entry có tag lớn nhất theo quy tắc. Để deterministic, cần giải quyết ties một cách xác định, ví dụ `(timestamp, actorId)`.

### 7.1. Ca kiểm thử đồng thời

~~~text
A writes phone = 0901, tag (10, A)
B writes phone = 0902, tag (11, B)

Merge(A,B) returns B.
Merge(B,A) must also return B.
~~~

Nếu comparator thống nhất và total order deterministic, LWW merge có thể thỏa ACI đối với state register thích hợp.

### 7.2. Deterministic không có nghĩa đúng nghiệp vụ

Người dùng sửa `shippingAddress` tại A; người khác sửa `note` tại B. LWW cho **toàn document** có thể loại bỏ một trong hai trường thay đổi dù hai thao tác không xung đột trên trường.

Cần quyết định merge **theo document, field, operation hoặc domain entity**. Không có một policy toàn cục đúng cho mọi attribute.

### 7.3. Clock skew

~~~text
Real time:
  T1: A writes x=1, A clock +5 minutes.
  T2: B writes x=2, B clock -2 minutes.
  T2 occurs after T1.
~~~

Nếu so client wall-clock timestamps, A có thể thắng dù B diễn ra sau theo thời gian thực.

**Test phải phân biệt “LWW theo timestamp” và “last operation theo thời gian thực”.** Hệ thỏa policy LWW không tự có linearizability.

### 7.4. Ties và non-determinism

Nếu hai giá trị có tag cùng timestamp mà node A chọn giá trị đến trước, node B chọn giá trị đến sau, replicas có thể diverge.

Cần tie-break có total ordering ổn định hoặc giữ multi-value conflict. Random tie-break trên từng replica là nguy hiểm.

### 7.5. Delete trong LWW

Một delete là một trạng thái/tombstone có version. Nếu chỉ xóa field vật lý, replica cũ gửi lại value trước đó có thể làm data “sống lại”. Phần tombstone sẽ được kiểm riêng.

---

## 8. Multi-value register và sibling resolution

Một số hệ/phương pháp lưu nhiều value khi phát hiện concurrent writes, thay vì tự chọn một bằng timestamp.

~~~text
Replica A: profile nickname = "Lan"
Replica B: profile nickname = "Mây"

After sync:
  siblings = {"Lan", "Mây"}
~~~

Đây có thể là **một trạng thái hội tụ đúng của hệ** nếu policy hứa giữ các lựa chọn chưa thể phân xử.

### 8.1. Không áp oracle “cuối cùng chỉ còn một value”

Nếu multi-value register cố ý giữ concurrency, test yêu cầu đúng **tập siblings/version contexts**, không bắt buộc chỉ một scalar.

### 8.2. Ứng dụng phải giải quyết

Khi người dùng chọn `"Mây"` sau khi nhìn thấy hai siblings, lần write mới phải mang causal context phù hợp để biểu diễn đã quan sát và quyết định về các giá trị đó.

Nếu thiếu context, hệ có thể tạo thêm sibling hoặc không xóa được xung đột cũ.

### 8.3. Sibling explosion

Nếu thiết bị offline lâu, writer churn cao hoặc ứng dụng không xử lý siblings, số phiên bản cùng tồn tại có thể tăng. Test cần đo:

- Số conflict branches.
- Bytes/version metadata.
- Thời gian merge.
- Số thao tác manual resolution.
- Khả năng dọn causal history sau resolve.

### 8.4. Không để người dùng chọn khi bất biến tự động cần bảo vệ

Giữ hai siblings của một “ghế đã bán cho ai” không giải quyết được hai lời hứa mua vé đã phát sinh. Domain cần authority/conditional grant chứ không chỉ UI resolve sau đó.

---

## 9. CRDT theo loại dữ liệu: test phải hợp semantics

| Loại | Ví dụ | Lợi ích | Ranh giới cần test |
|---|---|---|---|
| G-Counter | Lượt event cộng dồn theo replica | Increment có thể hội tụ | Không decrement, không quota |
| PN-Counter | Cộng và trừ qua hai G-Counter | Hội tụ tăng/giảm | Không tự giữ giá trị không âm |
| G-Set | Tập chỉ thêm | Union đơn giản | Không hỗ trợ xóa |
| OR-Set | Tập add/remove với causal dots | Quy tắc concurrent add/remove rõ | Tombstone/dot GC, actor metadata |
| LWW Register | Giá trị có tag ưu tiên | Deterministic selection | Mất update, clock skew |
| MV-Register | Giữ concurrent versions | Không âm thầm mất xung đột | Application resolution |
| Sequence CRDT | Collaborative list/text | Merge concurrent edits | Ordering/metadata size, intention |
| Map CRDT | Nhiều field kiểu CRDT | Merge có cấu trúc | Mixed field policy, delete map entries |

### 9.1. G-Counter

Mỗi replica giữ một thành phần đếm không giảm:

~~~text
A component = 3
B component = 2

State = {A:3, B:2}
Value = 5
~~~

Merge chọn max theo từng replica:

\[
merge(a,b)[i]=\max(a[i],b[i]).
\]

Nếu A nhận lại cùng state của B hai lần, max không làm counter bị cộng trùng.

### 9.2. PN-Counter

Sử dụng hai G-Counters `P` và `N`:

\[
value=\sum_i P_i-\sum_i N_i.
\]

Merge riêng từng vector bằng max. Kết quả hội tụ khi state trao đổi đủ.

Nhưng hai region cùng thấy `available=1` rồi tự trừ một mỗi bên có thể khiến giá trị cuối `-1`. **Tính hội tụ không đồng nghĩa bảo đảm số không âm**.

### 9.3. OR-Set

Một add gắn “dot” duy nhất như `(actor, sequence)`. Remove chỉ có thể loại bỏ những dot đã quan sát theo semantics add-wins tương ứng.

~~~text
Initial: no X.

A concurrently add X with dot A:1.
B concurrently remove X without seeing A:1.

After merge, X remains in add-wins OR-Set.
~~~

Nếu nghiệp vụ mong remove-wins, đây là **policy mismatch**, không phải bug của add-wins OR-Set.

### 9.4. Sequence editing

Hai client cùng chèn ký tự vào vị trí gần nhau có thể được hội tụ thành một chuỗi deterministic, nhưng **ý định văn bản** (ví dụ thứ tự câu) vẫn có thể không giống mong đợi. Test cần cả tính hội tụ và domain-specific semantic expectations.

---

## 10. Ma trận kiểm thử nền tảng

Một bộ kiểm thử nên phân nhóm theo thao tác, lịch sử và sự cố:

| ID | Tình huống | Fault/Concurrency | Oracle quan trọng |
|---|---|---|---|
| C01 | Một write, replica chậm | Delay một đường | Cuối cùng các replica thấy state hợp lệ |
| C02 | Hai write cùng value | Duplicate/reorder | Không tạo side effect mới ngoài policy |
| C03 | Hai write khác value | Concurrent partition | LWW/MV resolution đúng quy tắc |
| C04 | Concurrent add hai phần tử | A/B offline | Nếu policy set-union, giữ cả hai |
| C05 | Concurrent increments | Out-of-order | Tổng đếm đúng theo CRDT semantics |
| C06 | Duplicate delta delivery | Gửi lại 3 lần | Idempotence/dedup theo protocol |
| C07 | Remove vs concurrent add | Partition | Add-wins hoặc remove-wins như contract |
| C08 | Delete rồi stale replica trở lại | Long outage | Không resurrect sai |
| C09 | TTL hết hạn không đồng thời | Clock skew | Expiry semantics đúng |
| C10 | Clock drift | A nhanh/B chậm | LWW tie/order theo policy; không tự hứa real-time |
| C11 | Replica crash khi sync | Restart giữa merge | Không mất committed updates theo contract |
| C12 | Anti-entropy gián đoạn | Stream reset | Replay/checkpoint đúng, có hội tụ |
| C13 | Schema phiên bản cũ/mới | Mixed-version rollout | Merge tương thích hoặc reject rõ |
| C14 | Rebalance ownership | Membership change | Không bỏ key/version/tombstone |
| C15 | Global read model | CDC delay | Source và index freshness có contract riêng |
| C16 | Network heal nhưng write liên tục | Không có quiet period | Kiểm theo watermark/chunk thay vì value đứng yên |
| C17 | Business invariant | Hai vùng cùng cấp tài nguyên | Không double grant; hội tụ chưa đủ |
| C18 | Retry write timeout | Response lost | Idempotent intent, không duplicate |
| C19 | Metadata compaction | GC causal context | Không phá future convergence |
| C20 | Partial region outage | Một phía chưa kết nối | Không hứa hội tụ trước khi có đủ điều kiện |
| C21 | Concurrent field updates | A sửa field X, B sửa Y | Preserve/loss đúng per-field policy |
| C22 | Read under replication lag | Stale read | Không nhầm eventual convergence với RYW |
| C23 | Failover/restart sau ACK | Node mới active | Durability/commit contract đúng |
| C24 | Duplicate event từ broker | Consumer replay | Idempotent apply và consistent read model |

**Không phải mọi engine đều có cùng mô hình xung đột.** Với single-leader system, concurrent client writes có thể được primary serialize; với multi-region active-active, hai writes có thể được nhận ở hai vùng rồi resolve sau.

---

## 11. Thiết kế test C01: một write và một replica chậm

### Setup

~~~text
Key K = v0
A/B/C đã đồng bộ v0.

Network A -> C bị trì hoãn.
Client ghi K=v1 theo write contract.
~~~

### Steps

1. Ghi lại `requestId`, version và write concern/consistency mode.
2. Gửi write qua đường được cho phép.
3. Kiểm tra response ACK và phân loại durability.
4. Đọc từ A/B/C theo read modes đã quy định.
5. Gỡ network delay.
6. Kích hoạt/chờ anti-entropy/replication theo cơ chế hỗ trợ.
7. Poll tới deadline đo.
8. So sánh state và metadata cần thiết.

### Oracle

- Nếu write đã committed theo policy, cuối cùng những replica còn nằm trong replication scope phải thu được version phù hợp khi điều kiện đồng bộ thỏa.
- Không được kết luận một read stale ở C **trước khi mạng hồi phục** là vi phạm eventual consistency.
- Nếu write chỉ được ACK yếu và bị rollback hợp lệ sau failover, expected state khác; test phải nêu rõ write concern.

### Dữ liệu cần lưu

~~~text
ackType
committedVersion
replicaReadVersions
replicationLagAtHeal
timeToConverge
repairRounds
~~~

---

## 12. Thiết kế test C03: hai concurrent writes khác nhau

### Setup

~~~text
Initial K="DRAFT" on A/B.

Partition A | B.

At A:
  Write K="READY" with metadata MA.

At B:
  Write K="CANCELLED" with metadata MB.
~~~

### Oracle theo policy

**Nếu LWW:** giá trị cuối là record thắng theo comparator **được công bố**, không tự là write đến server cuối cùng.

**Nếu MV-register:** expected cuối là tập concurrent versions, trừ khi causal context cho biết một update thực sự thay thế update kia.

**Nếu domain state machine:** hai transition có thể cần bị từ chối ở một phía theo authority/conditional transition. Không phải mọi business status đều merge được bằng cách chọn một string.

### Các biến thể cần test

- A nhận delta của B trước, B nhận delta của A sau.
- Cả hai nhận cùng một delta hai lần.
- Timestamps bằng nhau.
- Writer ID tie-break khác nhau.
- Một replica restart ngay sau merge.
- Một write timeout nhưng vẫn được committed sau.
- Schema version khác nhau giữa A và B.

### Kết quả sai phổ biến

Hai replica cùng có `K="READY"` trong một lần test, nhưng lần replay với thứ tự message khác lại cùng có `K="CANCELLED"` mặc dù metadata giống nhau. Nếu policy yêu cầu deterministic result, đó là lỗi **thiếu tính quyết định**, dù mỗi lần riêng lẻ cuối cùng vẫn hội tụ.

---

## 13. Thiết kế test C04: hai thao tác thêm độc lập

### Setup

~~~text
Initial wishlist = {book}

A offline:
  add camera

B offline:
  add laptop
~~~

### Expected theo từng loại dữ liệu

- **LWW document:** có thể chỉ giữ một nhánh nếu policy nói vậy.
- **Add-only G-Set:** expected `{book,camera,laptop}`.
- **OR-Set:** expected có cả hai additions nếu không có remove hợp lệ tác động tới chúng.
- **Custom per-field merge:** tùy semantics của field.

### Assert quan trọng

Không dùng một expected value áp cho mọi policy. Nếu sản phẩm hứa “không mất thao tác add độc lập”, LWW toàn-document **không thỏa yêu cầu sản phẩm**, ngay cả khi implementation LWW hoạt động đúng thiết kế.

### Test thêm

Nếu hai client cùng add `camera`:

- G-Set vẫn chỉ có một `camera` vì semantics set.
- Một danh sách cho phép duplicate có thể có hai item.
- OR-Set có thể giữ hai dots nội bộ dù user-visible element chỉ xuất hiện một lần.
- Test metadata không nên đòi xóa mọi dấu vết dot ngay khi logical set đã hội tụ.

---

## 14. Thiết kế test remove-vs-add và delete resurrection

Đây là nhóm lỗi thường chỉ xuất hiện khi một replica offline lâu.

### 14.1. Delete cũ gặp replica lỗi thời

~~~text
T0: A/B/C có K=v1.
T1: C offline.
T2: A/B xác nhận DELETE K, lưu tombstone version 9.
T3: Một thời gian dài trôi qua.
T4: C trở lại, vẫn có K=v1 version 7.
~~~

Nếu A/B đã **garbage collect tombstone** mà không còn bằng chứng xóa theo protocol, update cũ từ C có thể khiến K xuất hiện lại.

### 14.2. Test phải đi qua GC horizon

Một test chỉ chờ tới T2 rồi đọc thấy K bị xóa sẽ bỏ lỡ lỗi. Cần thêm:

1. Để C offline qua khoảng retention theo test environment.
2. Kiểm tra repair/tombstone GC policy.
3. Cho C tái kết nối.
4. Chạy đồng bộ theo cơ chế của DBMS.
5. Đọc lại K trên mọi replica.
6. Xác nhận không có hồi sinh trái contract.

Không thay đổi cấu hình retention nguy hiểm trên production; dùng staging có quyền và dữ liệu riêng.

### 14.3. Remove và add concurrent

Nếu A remove phần tử X nhưng B offline add X:

- Add-wins OR-Set có thể giữ X.
- Remove-wins set có thể loại X.
- Delete-wins LWW có thể phụ thuộc tag.
- Domain có thể yêu cầu manual review.

Test phải viết rõ **quy tắc**, không chỉ assert giá trị cảm tính.

### 14.4. TTL khác DELETE explicit

TTL có thể phụ thuộc thời gian và sự kiện hết hạn; một số engine lưu expiry metadata theo cách riêng. Test phải xem:

- Clock nào quyết định expiry?
- TTL được tính từ write nào?
- Replication của expiry/tombstone ra sao?
- Stale replica có thể đưa dữ liệu hết hạn trở lại không?
- Read path có chủ động ẩn record đã expired chưa?

Không tự kết luận TTL là delete nguyên tử trên mọi replica đúng cùng microsecond.

---

## 15. Kiểm thử clock skew, monotonic clock và timestamp tie

### 15.1. Kịch bản

~~~text
A clock: +90 seconds
B clock: -120 seconds

Real-time:
  A writes value=1.
  A's write completes.
  B later writes value=2.
~~~

Nếu policy so wall-clock timestamp, A có thể thắng. Đây có thể là **hành vi hợp lệ theo LWW timestamp**, nhưng không phải latest theo thời gian thực.

### 15.2. Những test cần có

- Clock lệch dương/âm.
- Hai writes cùng timestamp.
- Client gửi timestamp tương lai xa.
- Node reboot sau khi clock bị chỉnh.
- Update từ offline device gửi lên sau nhiều giờ.
- Timezone/serialization đổi mà version ordering không đổi.
- Tag gồm actor ID hay không.
- Merge sau restart có deterministic không.

### 15.3. Tách yêu cầu

**Nếu product chỉ cần deterministic LWW:** assert comparator trả cùng winner ở mọi replica.

**Nếu product cần causal ordering:** phải dùng causal metadata/ordering protocol thích hợp.

**Nếu product cần linearizability:** cần protocol đáp ứng thứ tự thời gian thực của các operation trong phạm vi hỗ trợ, không chỉ chọn max timestamp.

### 15.4. Không dùng wall-clock test runner làm oracle duy nhất

Hai test clients có đồng hồ lệch không thể dùng timestamp từng máy để chứng minh một operation hoàn tất trước operation khác. Khi cần lịch sử real-time, test runner phải thu thập invocation/response intervals với phương pháp đồng bộ/điều phối thích hợp.

---

## 16. Duplicate delivery, reordering và retry

Replication/CDC/broker thường có thể giao một event nhiều lần hoặc lệch thứ tự trong những điều kiện cho phép.

### 16.1. Một event được xử lý hai lần

~~~text
Event E1: AddItem("camera")
Delivered to B twice.
~~~

Nếu model là set add idempotent, user-visible kết quả có thể vẫn chỉ một camera. Nếu đó là nghiệp vụ “tính tiền 100.000 VND” thì duplicate có thể là double-charge.

**Idempotent CRDT merge không biến mọi business side effect thành idempotent.**

### 16.2. Hai events đảo thứ tự

~~~text
E1: set order status=PAID
E2: set order status=REFUNDED
~~~

Nếu contract yêu cầu `E2` là transition sau E1, xử lý E2 rồi E1 theo arrival order có thể sai. Cần version/state machine/ordered stream hoặc phương pháp reconciliation có cơ sở.

### 16.3. Replay từ checkpoint

Cho consumer xử lý E1/E2, crash trước khi commit offset, rồi xử lý lại. Assert:

- Final DB state hợp policy.
- Outbox/inbox dedup không làm phát payment/notification lặp trái contract.
- Watermark/checkpoint chỉ tiến khi dữ liệu đã được áp dụng theo quy trình.
- Backlog có thể drain.

### 16.4. Chỉ test với event IDs cố định

Nếu retry tạo `eventId` mới, dedup theo event ID không biết đó là cùng một ý định nghiệp vụ. Test phải xác định **ID của logical operation** và **ID của delivery attempt**.

---

## 17. Anti-entropy và repair: hội tụ cần một cơ chế vận chuyển đủ tin cậy

Ngay cả khi merge là ACI, replicas không thể hội tụ nếu một số update **không bao giờ tới nơi cần thiết**.

### 17.1. Giai đoạn kiểm tra

~~~mermaid
sequenceDiagram
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C
    Note over A,C: B offline, A/C tiếp tục nhận update
    A->>C: Replicate update E1
    Note over B: Chưa có E1
    B-->>A: Rejoin / anti-entropy
    A->>B: Digest/range comparison
    A->>B: Missing state/delta E1
    B-->>A: Checkpoint/ACK theo protocol
    Note over A,C: Quan sát tất cả replica sau repair
~~~

Sơ đồ chỉ minh họa ý tưởng. Cassandra repair, DynamoDB replication, MongoDB oplog replication, Redis replication hoặc một CRDT store có cơ chế đồng bộ rất khác nhau.

### 17.2. Test khởi động lại sync nhiều lần

1. Bắt đầu anti-entropy.
2. Trì hoãn một số message.
3. Crash/restart một node hoặc consumer trong staging.
4. Phục hồi kết nối.
5. Cho job restart/retry.
6. Kiểm tra không bỏ sót key/range và state cuối hợp lệ.

### 17.3. Thông điệp ACK chưa chắc đã durable

Một node nhận delta vào memory rồi ACK nhưng crash trước persistence có thể mất delta tùy engine. Nếu contract dựa trên durable acknowledgment, test phải bao gồm disk persistence/fsync semantics.

### 17.4. Repair có thể cần đủ lịch sử

Nếu đồng bộ dựa trên changelog, dữ liệu có thể không bắt kịp khi:

~~~text
Offline duration > log retention window.
~~~

Khi đó hệ cần full resync/rebuild theo protocol, hoặc phải báo không thể tự repair. Không hứa convergence nếu nguồn thông tin đã không còn.

### 17.5. Backpressure và repair backlog

Một replica quá chậm có thể bị backlog tăng liên tục. Test nên đo lag, update generation rate, effective repair throughput và khả năng catch-up sau khi traffic ổn định.

---

## 18. Kiểm thử failover, membership và migration

Một test hội tụ không thể giả định replica set bất biến nếu hệ hỗ trợ scale-out, rebalancing hoặc leader changes.

### 18.1. Node mới tham gia

Một node mới nhận snapshot rồi delta:

~~~text
Snapshot at version K.
Then replay updates K+1...K+n.
~~~

Test phải đảm bảo:

- Không thiếu khoảng giữa snapshot và delta.
- Không apply delta sai thứ tự khi semantics cần ordering.
- Không trả write/strong read từ node mới trước khi đủ điều kiện.
- Tombstone và conflict metadata được chuyển đủ.
- Rejoin tiếp tục đúng sau crash.

### 18.2. Node cũ quay lại

Một node cũ có state stale có thể:

- Bắt kịp và trở thành replica hợp lệ.
- Bị re-seed.
- Bị loại khỏi membership.
- Cần bị fence khỏi quyền ghi cũ.

Không cho nó phát authoritative write trên metadata phiên bản cũ nếu contract yêu cầu single-owner.

### 18.3. Split-brain và conflict resolution

Nếu hệ chọn multi-writer eventual resolution, hai vùng có thể phát sinh concurrent writes rồi merge. Nếu hệ chọn leader consensus/majority để giữ linearizability, một phía có thể phải từ chối write trong partition.

**Không ép test phải cho cả hai phía ACK khi sản phẩm không hứa availability trong minority partition.**

### 18.4. Membership churn

Khi actor IDs hoặc replicas được thêm/bớt thường xuyên, causal metadata có thể tăng hoặc bị GC. Test cần quan sát state metadata và hiện tượng lost-update sau khi actor cũ quay lại.

---

## 19. Hội tụ khác linearizability và serializability

Một hệ LWW có thể đưa mọi replica về cùng value nhưng vẫn cho phép read trả dữ liệu cũ sau một write đã được xác nhận, tùy read/write consistency contract.

### 19.1. Convergence là một tính chất dài hạn

Nó nói về trạng thái cuối sau replication/repair trong một số giả định.

### 19.2. Linearizability là tính chất lịch sử theo thời gian thực

Nếu write `x=2` đã hoàn tất trước read `x`, không có write khác, và phạm vi hứa linearizability, read không được trả `x=1`.

Một lần poll thấy hai replica cuối cùng cùng bằng 2 **không chứng minh** tất cả reads trước đó linearizable.

### 19.3. Serializability của transaction là câu hỏi riêng

Hai tài khoản cần chuyển tiền:

~~~text
A.balance -= 100
B.balance += 100
~~~

Mỗi key có thể hội tụ riêng nhưng tổng số dư toàn hệ có thể sai nếu hai cập nhật không atomic/serializable khi workflow yêu cầu.

### 19.4. CRDT không thay transaction cho mọi invariant

Một PN-Counter hội tụ và có thể âm. Một G-Set hội tụ nhưng không đảm bảo “tối đa một người sở hữu ghế”. Dùng CRDT để lưu thông tin có thể merge an toàn, và dùng authority/escrow/transaction khi phải phối hợp cấp phát tài nguyên khan hiếm.

---

## 20. Oracle nghiệp vụ: các replica giống nhau chưa đủ

Hãy xác định các invariant **trước khi chọn conflict policy**.

| Bài toán | Bất biến | Merge đơn giản có đủ? |
|---|---|---|
| Favorites | Hai thao tác thêm độc lập không bị mất | Set union/OR-Set có thể phù hợp |
| Profile display name | Cần một tên cuối theo lựa chọn người dùng | LWW hoặc manual resolution tùy yêu cầu |
| Inventory | Confirmed ≤ capacity | LWW counter thường không đủ |
| Wallet/ledger | Không tạo/mất tiền trái rule | Cần transaction/ledger semantics |
| Chat unread count | Đếm event đúng, có xử lý retry | Counter/dedup với semantics rõ |
| Unique username | Một tên không cấp cho hai account | Cần authority/conditional uniqueness |
| Event log | Không xử lý event nghiệp vụ hai lần | Idempotency key/inbox |
| Wishlist remove/add | Add-wins hay remove-wins? | Chỉ đúng khi policy được quyết định |
| ACL/security role | Không giữ quyền đã bị thu hồi | Merge cần ưu tiên revoke/authority |
| Order status | Không `REFUNDED -> PAID` trái workflow | State machine/versioned transition |

### 20.1. Oversell test

~~~text
Capacity=1.
A offline confirms reservation A.
B offline confirms reservation B.

After heal:
  Both replicas agree available=0.
~~~

Test `converged=true` **không được pass nghiệp vụ**. Phải assert:

\[
confirmedAllocations\le1.
\]

Nếu hệ yêu cầu hoạt động offline trong cả hai vùng, phải thiết kế quyền phân bổ trước như escrow/quota partitioning hoặc chấp nhận một chính sách bù trừ có mô tả rõ; không thể tự hứa cả hai quyền cấp phát cuối cùng đồng thời mà không có phối hợp phù hợp.

### 20.2. Security invariant thường không chấp nhận LWW tùy tiện

Nếu quản trị viên revoke quyền ở một vùng nhưng vùng khác cập nhật profile, một merge toàn document có thể phục hồi role đã bị gỡ. Test cần kiểm tra **quyền bị thu hồi vẫn bị thu hồi** theo contract.

### 20.3. Causal order trong workflow

Một trạng thái `PAID` có thể cần chứng cứ payment committed; `REFUNDED` cần liên hệ một payment đã thực hiện. Trộn các string status bằng `max(timestamp)` có thể tạo trạng thái hợp cú pháp nhưng vô căn cứ nghiệp vụ.

---

## 21. Chọn mức quan sát đúng khi kiểm thử

Một test có thể đọc dữ liệu qua nhiều đường:

~~~text
Client -> source leader/base table
Client -> secondary replica
Client -> cache
Client -> global secondary index
Client -> search index
Client -> analytics read model
~~~

### 21.1. Source state và read model có hai thời gian hội tụ

Source A/B có thể đã đồng bộ, nhưng search index vẫn chậm 20 giây. Đừng đánh giá thuật toán source merge sai chỉ vì CDC chưa chạy xong; đồng thời đừng tuyên bố UX “đã cập nhật khắp nơi” nếu sản phẩm hứa query qua search mà search chưa theo kịp.

### 21.2. Watermark theo đường đọc

Có thể theo dõi:

~~~text
sourceCommitVersion = 120
replicaBAppliedVersion = 120
searchAppliedVersion = 117
analyticsAppliedVersion = 110
~~~

Tên trường minh họa. Test có thể đợi từng downstream tới mốc cần thiết, thay vì đợi một khoảng ngủ tùy ý.

### 21.3. So sánh cùng consistency mode

Nếu region A đọc strong source, region B đọc eventual secondary, kết quả khác nhau ở thời điểm T không tự là merge bug. Phải đặt read concern/consistency level và phạm vi tương ứng khi so oracle.

### 21.4. Read-your-writes là một oracle riêng

Một session đã thấy version 120 có thể yêu cầu không đọc lùi về 117, dù toàn hệ dùng eventual replication. Điều đó đòi session token/routing/watermark hoặc read path phù hợp, không tự đến từ hội tụ về sau.

---

## 22. Ma trận fault injection có kiểm soát

Kiểm thử thực tế cần thay đổi **một trục lỗi** trước, sau đó tổ hợp những lỗi có giá trị.

| Fault | Cách mô phỏng ở staging | Điều quan sát |
|---|---|---|
| Network partition | Chặn liên lạc giữa nhóm replica | Hai phía xử lý write ra sao |
| Latency | Delay một đường replication | Replica lag, read staleness |
| Packet loss | Giảm xác suất delivery có kiểm soát | Retry và convergence |
| Message duplication | Replay event/delta từ harness | Idempotence |
| Reordering | Đảo thứ tự sự kiện có thể đảo | Merge deterministic |
| Process crash | Restart ở mốc append/merge | Recovery, missing updates |
| Disk pressure | Giới hạn I/O an toàn ở test env | Repair backlog |
| Clock skew | Dùng clock fault tool trong môi trường riêng | LWW/TTL behavior |
| Stale client | Offline rồi reconnect | Causal context, sibling |
| Expired log | Giữ replica offline qua retention trong staging | Full resync/repair |
| Tombstone GC | Dùng retention ngắn dành cho test | Delete resurrection |
| Membership change | Join/leave/rebalance theo tool hỗ trợ | Metadata continuity |
| Version skew | Rolling upgrade trong test cluster | Schema compatibility |
| Concurrent load | N writer theo cùng key/partition | Conflict rate, invariant |
| Failover | Đổi leader theo quy trình test | Commit vs uncommitted state |
| Consumer redelivery | Crash trước broker ACK | Dedup/side effects |

**An toàn:** không gây partition, xóa dữ liệu, làm lệch đồng hồ hoặc ép GC/repair trên production ngoài quy trình đã được phê duyệt. Bài tập chỉ nên dùng staging/disposable test cluster.

---

## 23. Thiết kế harness: ghi lịch sử và phát lại xác định

Một test harness có thể tách các vai trò:

~~~mermaid
flowchart TD
    S["Scenario generator"] --> H["History recorder"]
    S --> F["Fault scheduler"]
    S --> W["Clients/writers"]
    W --> A["Replica/Region A"]
    W --> B["Replica/Region B"]
    F --> A
    F --> B
    A --> O["State observer"]
    B --> O
    O --> C["Convergence + invariant checker"]
    H --> C
    C --> R["Artifacts: history, seed, metrics"]
~~~

### 23.1. Lưu random seed

Ví dụ:

~~~text
seed=3872026
writers=4
operations=500
faults=[partition(A,B), delay(A,C), duplicate(E17)]
healingAt=step480
~~~

Nếu test fail, cùng seed giúp tái tạo thứ tự operations do generator sinh. Nhưng network scheduling thực tế còn có nondeterminism, nên lưu cả timeline quan sát được và fault trigger IDs.

### 23.2. Lưu invocation và response

~~~json
{
  "operationId": "op-001",
  "writer": "client-A",
  "kind": "ADD",
  "key": "wishlist:42",
  "value": "camera",
  "invokeMonotonicNanos": 100000,
  "respondMonotonicNanos": 110000,
  "result": "ACK",
  "context": {
    "region": "A",
    "version": "A:8"
  }
}
~~~

Đây là event minh họa trong một test runner. `System.nanoTime()` trên các process khác nhau không phải một global timestamp có thể so trực tiếp; muốn so thời gian thực đa máy cần cách điều phối/đồng hồ phù hợp.

### 23.3. Outcome unknown

Một write timeout có thể đã được lưu. Nếu harness đơn giản bỏ nó khỏi expected operations, test có thể báo false positive hoặc false negative.

Cần theo dõi:

- Attempt đã gửi?
- ACK nhận được?
- Authoritative state đã ghi?
- Request ID/idempotency ID?
- Có thể đọc để reconcile?
- Nếu outcome unknown, oracle chấp nhận những lịch sử hợp lệ nào?

### 23.4. Canonicalization

Nếu logical state là set, so sánh set không phụ thuộc thứ tự array trong JSON. Nếu state gồm map, chuẩn hóa key order. **Không chuẩn hóa bỏ mất causal metadata/tombstone mà test đang cần bảo vệ.**

---

## 24. Kiểm thử convergence có giới hạn thời gian

Một cách tổ chức:

~~~text
Given:
  Write history H and chosen policy P.

When:
  All writes in H are stopped.
  Faults are removed.
  Network and replication paths are healthy.
  Repair/anti-entropy can make progress.

Then:
  Poll eligible replicas until deadline D.
  Assert semantic state equivalence according to P.
  Assert domain invariants.
  Record time-to-converge.
~~~

### 24.1. Giả định fair progress

Nếu một replica luôn offline, không thể coi đến deadline D mà nó chưa hội tụ là lỗi của cơ chế eventual consistency. Test phải phân biệt:

- **Convergence failure:** điều kiện đã đủ nhưng không tiến tới cùng state.
- **Environment blocked:** đường truyền/repair không hoạt động.
- **SLO violation:** có hội tụ nhưng chậm hơn mục tiêu vận hành.
- **Policy failure:** hội tụ về state sai business expectation.
- **Observation artifact:** read path stale dù source đã cùng state.

### 24.2. Không dừng ngay khi thấy bằng nhau một lần

Có thể chạy một khoảng observation stability hoặc trigger thêm repair/restart:

~~~text
T1: A/B equal at v10.
T2: Stale C rejoins and sends v7.
T3: A/B may regress due to incorrect tombstone/merge.
~~~

Một test chỉ so A/B ở T1 chưa bao phủ sự kiện C.

### 24.3. Với write liên tục

Nếu không thể dừng writes, có thể gắn watermark/version:

~~~text
Expected updates up to seq=1000.
All eligible replicas have applied through seq=1000.
~~~

Sau đó so logical projection đến watermark; không đòi tất cả replicas có byte-for-byte state bằng nhau ở cùng giây khi thêm writes liên tục.

### 24.4. Thời gian hội tụ có phân phối

Đo p50/p95/p99 của time-to-converge theo scenario và key cohort, không chỉ một giá trị trung bình. Cần xem backlog size, network RTT, anti-entropy schedule và tải foreground.

---

## 25. Java: mô hình G-Counter state-based CRDT

Dưới đây là ví dụ minh họa dùng **Java 17**: mỗi replica có một thành phần đếm không giảm, merge lấy max từng thành phần, tổng đọc bằng sum.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public final class GCounter {

    private final Map<String, Long> components;

    private GCounter(Map<String, Long> data) {
        this.components = Map.copyOf(data);
    }

    public static GCounter empty() {
        return new GCounter(Map.of());
    }

    public static GCounter from(Map<String, Long> values) {
        Objects.requireNonNull(values, "values");
        values.forEach((actor, count) -> {
            if (actor == null || actor.isBlank()
                    || count == null || count < 0) {
                throw new IllegalArgumentException(
                    "Invalid actor/counter"
                );
            }
        });
        return new GCounter(values);
    }

    public GCounter increment(String actor) {
        if (actor == null || actor.isBlank()) {
            throw new IllegalArgumentException("actor required");
        }

        Map<String, Long> next = new HashMap<>(components);
        long current = next.getOrDefault(actor, 0L);
        next.put(actor, Math.addExact(current, 1L));
        return new GCounter(next);
    }

    public GCounter merge(GCounter other) {
        Objects.requireNonNull(other, "other");

        Map<String, Long> merged = new HashMap<>(components);
        other.components.forEach((actor, right) ->
            merged.merge(actor, right, Math::max)
        );
        return new GCounter(merged);
    }

    public long value() {
        return components.values().stream()
            .reduce(0L, Math::addExact);
    }

    public Map<String, Long> components() {
        return components;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof GCounter c
            && components.equals(c.components);
    }

    @Override
    public int hashCode() {
        return components.hashCode();
    }
}
~~~

### 25.1. Vì sao chọn max chứ không cộng map?

Giả sử A đã có `A:3`; B đã nhận và lưu `A:3`. Nếu merge cộng, kết quả có thể thành `A:6` dù chỉ có ba increments.

Merge max giữ đúng thông tin “đã quan sát đến số đếm 3 của actor A” và không cộng thêm khi nhận bản sao cùng state.

### 25.2. Ràng buộc của ví dụ

- Mỗi actor phải cập nhật **thành phần riêng** một cách có thứ tự, không cho hai process độc lập cùng increment cùng actor component rồi ghi đè.
- Map keys là actor IDs ổn định; actor churn/GC chưa được giải quyết.
- `Math.addExact` ném exception khi vượt `long`, không âm thầm overflow.
- Mã dùng immutable snapshots đơn giản, không phải triển khai CRDT store production.
- Không có persistence/transport/anti-entropy.
- Không phù hợp để tự bảo đảm giới hạn inventory.

### 25.3. Ví dụ trạng thái

~~~text
A starts empty.
A.increment(A) twice -> {A:2}

B starts empty.
B.increment(B) once  -> {B:1}

merge(A,B) = {A:2,B:1}, value=3
merge(B,A) = {A:2,B:1}, value=3
~~~

---

## 26. Java/JUnit 5: kiểm thử ACI

Dùng JUnit Jupiter cho ví dụ unit tests dưới đây.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;

public class GCounterPropertiesTest {

    private final GCounter a =
        GCounter.from(Map.of("A", 3L));

    private final GCounter b =
        GCounter.from(Map.of("A", 1L, "B", 2L));

    private final GCounter c =
        GCounter.from(Map.of("C", 4L));

    @Test
    void mergeIsCommutative() {
        assertEquals(
            a.merge(b),
            b.merge(a)
        );
    }

    @Test
    void mergeIsAssociative() {
        assertEquals(
            a.merge(b).merge(c),
            a.merge(b.merge(c))
        );
    }

    @Test
    void mergeIsIdempotent() {
        assertEquals(a, a.merge(a));
        assertEquals(b, b.merge(b));
    }

    @Test
    void repeatedReplicaDeliveryDoesNotDoubleCount() {
        GCounter merged = a.merge(b);
        GCounter repeated = merged.merge(b).merge(b);

        assertEquals(5L, repeated.value());
        assertEquals(merged, repeated);
    }

    @Test
    void interleavedUpdatesConvergeWhenStatesExchange() {
        GCounter aLocal = GCounter.empty()
            .increment("A")
            .increment("A");

        GCounter bLocal = GCounter.empty()
            .increment("B");

        GCounter stateAtA = aLocal.merge(bLocal);
        GCounter stateAtB = bLocal.merge(aLocal);

        assertEquals(stateAtA, stateAtB);
        assertEquals(3L, stateAtA.value());
    }
}
~~~

### 26.1. ACI là tính chất của phép merge đã triển khai

Các test này kiểm tra những ví dụ đại diện; chúng **chưa phải chứng minh toán học cho mọi state**. Kết hợp model/property-based testing với kiểm tra code và cơ sở lý thuyết để tăng độ tin cậy.

### 26.2. Unit test không thay integration test

GCounter merge đúng nhưng transport đánh mất một update thì replicas vẫn không hội tụ. Tương tự, merge đúng mà storage xóa metadata quá sớm vẫn có thể gây lỗi về sau.

### 26.3. Không sử dụng GCounter để giảm tồn kho

GCounter không hỗ trợ decrement. Nếu dùng PN-Counter để trừ lượng tồn, nó có thể hội tụ về số âm. Để giữ `available >= 0` cần transaction/escrow/conditional allocation phù hợp.

---

## 27. Java: property-style test với nhiều thứ tự merge

Ta có thể tạo bộ kiểm thử lặp nhiều dữ liệu và thứ tự khác nhau, dùng seed cố định để tái hiện.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Random;
import org.junit.jupiter.api.Test;

public class GCounterPermutationTest {

    @Test
    void mergingAllStatesConvergesRegardlessOfOrder() {
        List<GCounter> snapshots = List.of(
            GCounter.from(Map.of("A", 5L)),
            GCounter.from(Map.of("B", 7L)),
            GCounter.from(Map.of("A", 3L, "C", 2L)),
            GCounter.from(Map.of("B", 4L, "C", 9L))
        );

        GCounter expected = GCounter.empty();
        for (GCounter state : snapshots) {
            expected = expected.merge(state);
        }

        Random random = new Random(3872026L);

        for (int iteration = 0; iteration < 1000; iteration++) {
            List<GCounter> shuffled =
                new ArrayList<>(snapshots);

            Collections.shuffle(shuffled, random);

            GCounter actual = GCounter.empty();
            for (GCounter state : shuffled) {
                actual = actual.merge(state);
            }

            // Lặp lại một state để mô phỏng duplicate.
            actual = actual.merge(shuffled.get(0));

            assertEquals(
                expected,
                actual,
                "Failed iteration " + iteration
            );
        }

        assertEquals(21L, expected.value());
    }
}
~~~

### 27.1. Vì sao expected=21?

Các thành phần lớn nhất là:

~~~text
max A = 5
max B = 7
max C = 9
sum   = 21
~~~

### 27.2. Giới hạn của test này

- Chỉ thử 1.000 permutation có random seed, không bao phủ mọi trạng thái.
- Không mô phỏng genuine concurrent mutation trên cùng actor.
- Không thử persistence, transport, crash, GC hoặc network partition.
- Không kiểm business correctness của các events làm tăng counter.
- Không test khả năng cân bằng memory khi số actors tăng không giới hạn.

### 27.3. Property-based testing nâng cao

Nếu sử dụng một thư viện tạo dữ liệu (ví dụ jqwik hoặc framework tương đương), generator có thể sinh:

- Actor count 1..N.
- Thành phần counter 0..max.
- Duplicate snapshots.
- Arbitrary merge trees.
- Các trace increment/merge hợp lệ.
- Restart và replay checkpoints.

Shrinking giúp tìm trace nhỏ nhất gây lỗi. Tên/phiên bản thư viện cần phù hợp project; không bắt buộc dùng một framework cụ thể.

---

## 28. Test PN-Counter: hội tụ nhưng không bảo toàn giới hạn

Giả sử hệ ghi một PN-Counter cho số **đã bán**:

~~~text
Initial capacity=1
Sales counter P={A:0,B:0}

Partition A|B:
  A increments sale count -> P={A:1,B:0}
  B increments sale count -> P={A:0,B:1}

After merge:
  P={A:1,B:1}
  sold=2
~~~

State hội tụ đúng: **sold=2**. Nhưng:

\[
sold=2>capacity=1.
\]

### 28.1. Đây không phải bug merge

Lỗi nằm ở **cấp quyền ghi nghiệp vụ**: cả hai bên độc lập xác nhận tài nguyên khan hiếm mà không có token/quota/authority đủ điều kiện.

### 28.2. Hướng thiết kế đúng hơn

Tùy yêu cầu:

- Single authoritative allocation/transaction.
- Conditional update/CAS.
- Leader/quorum coordination cho resource.
- Escrow/quota pre-allocation sao cho tổng quyền cấp phát không vượt capacity.
- Reservation hold với conflict/compensation contract minh bạch.

### 28.3. Ca kiểm thử cần cả hai assert

~~~text
Assert convergence:
  All regions agree sold=2.   -> PASS

Assert business safety:
  sold <= capacity.           -> FAIL
~~~

Một test suite tốt giữ **hai kết quả độc lập**, không che dấu lỗi nghiệp vụ bằng thông báo “replication healthy”.

---

## 29. Test unique constraint và quyền sở hữu

Tình huống:

~~~text
Username "alex" chưa được dùng.

Region A offline: assign alex to User 101.
Region B offline: assign alex to User 202.

After heal, LWW selects User 202.
~~~

Cuối cùng mọi replica đều biết `alex -> User202`, nhưng Region A có thể đã gửi email “Bạn sở hữu alex” cho User101.

### 29.1. Invariant

\[
\forall username,\quad
\#\{\text{active authoritative owners}\}\le1.
\]

### 29.2. Conflict resolution sau cùng không sửa lời hứa đã phát

Nếu hệ hứa cấp tên độc quyền ngay lập tức ở cả hai vùng không phối hợp, test cần nêu conflict model/escrow hoặc không cho cả hai vùng xác nhận. LWW sau đó chọn winner chỉ giải quyết **stored value**, không đảo ngược tác động người dùng.

### 29.3. Test side effects

Kiểm tra:

- Có bao nhiêu email xác nhận được gửi?
- Hệ có trả 200/201 cho hai người?
- Có retraction/compensation được thiết kế?
- API có phân biệt `PENDING` và `CONFIRMED`?
- Retry có giữ cùng `requestId` không?

---

## 30. Kiểm thử schema evolution và mixed-version replicas

Một hệ phân tán có thể rolling upgrade, nên hai bản ứng dụng/replica có schema hoặc merge logic khác nhau.

### 30.1. Ví dụ

~~~text
V1 document:
  {name, email}

V2 document:
  {name, email, verifiedAt, consent}
~~~

Nếu V1 deserialize rồi serialize lại và bỏ unknown fields, nó có thể xóa `verifiedAt` hoặc `consent` mà V2 đã ghi.

### 30.2. Test bắt buộc

1. V1 write rồi V2 read.
2. V2 write rồi V1 read và update một field khác.
3. Đồng bộ hai bản có/không có field mới.
4. V1/V2 merge khi concurrent.
5. Restart/rollback deployment.
6. Tombstone/TTL với field mới.
7. Rebuild index từ dữ liệu mixed-version.

### 30.3. Invariant về backward compatibility

Nếu contract yêu cầu giữ unknown fields, test phải bảo đảm older writer không xóa fields ngoài phạm vi update. Nếu intentional schema migration loại bỏ field, phải có versioned policy rõ thay vì coi mất data là hợp lệ.

### 30.4. Merge function upgrade

Hai replica chạy hàm merge khác nhau có thể không có một normal form chung. Không tự giả định deterministic trong từng version đồng nghĩa convergence xuyên version.

---

## 31. Thiết kế test theo hệ NoSQL: đừng áp sai mô hình

### 31.1. Cassandra

Regular writes dùng replication và timestamp-based reconciliation trong nhiều đường dữ liệu; CL và RF quyết định điều kiện acknowledgment và replica read, còn repair/anti-entropy giúp đồng bộ.

Các ca cần cân nhắc:

- Concurrent writes cùng partition/column.
- Tie/clock skew của timestamp.
- Write timeout và retry.
- Replica down rồi repair.
- Tombstone GC và stale replica.
- TTL/expiring cells.
- `LOCAL_QUORUM` theo datacenter.
- LWT/Paxos cho conditional operations nếu cần business arbitration.

**Không kết luận CL=QUORUM làm mọi concurrent business update serializable/linearizable.** LWT có semantics khác regular writes.

### 31.2. DynamoDB global tables

DynamoDB là managed service, với global replication và conflict semantics phụ thuộc **loại global table, chế độ consistency và phiên bản/khả năng dịch vụ**.

Các ca test:

- Write tại hai regions nếu chế độ cho phép.
- Region lag hoặc partition.
- Conflict resolution policy hiện hành.
- Strong read ở base table so với eventual GSI.
- Conditional writes/transactions trong phạm vi contract.
- Global read-your-writes và region failover.
- TTL/delete và replication delay.
- Retry với client request token/idempotency ở API phù hợp.

Không mặc định mọi global-table mode là LWW giống nhau, cũng không suy global linearizability từ `ConsistentRead` trên một đường đọc địa phương.

### 31.3. MongoDB replica set

MongoDB replica set thông thường là primary–secondary, không phải hệ multi-writer độc lập hai primary được hỗ trợ như một LWW document store.

Ca test phù hợp:

- Primary failover trong write.
- `w:1` vs majority acknowledgment và rollback.
- Read concern majority/linearizable trong scope hỗ trợ.
- Retryable writes/transactions và unknown commit outcome.
- Secondary lag và causal session.
- Sharded routing/migration nếu có.
- Application merge dữ liệu offline nếu mobile clients gửi version khác nhau.

**Không giả tạo kịch bản “hai primary MongoDB độc lập cùng commit vào một replica set” như hành vi thông thường được hỗ trợ.**

### 31.4. CouchDB-style revision conflicts

Một hệ document replication có revision trees/conflict branches có thể lưu nhiều revisions của cùng document; ứng dụng cần xem policy chọn winning revision và xử lý conflicts.

Test:

- Hai nhánh sửa offline.
- Replication hai chiều.
- Winning revision deterministic theo contract.
- Phát hiện nhánh không thắng.
- Application resolve và tạo revision mới.
- Delete/compaction/revision history.
- Reconnect nhiều lần.

Không coi “winning revision hiển thị giống nhau” là bằng chứng những nhánh xung đột đã được xử lý có chủ đích.

### 31.5. Redis primary/replica và Active-Active variants

Redis primary/replica thường có asynchronous replication; sau failover có thể có acknowledged writes chưa hiện diện ở replica mới tùy policy.

Nếu dùng một sản phẩm Redis Active-Active/CRDT cụ thể, phải test theo **loại dữ liệu và merge semantics được công bố**. Không gán CRDT semantics cho Redis OSS primary/replica chỉ vì cùng nhãn Redis.

### 31.6. Azure Cosmos DB

Các cấu hình consistency, multi-region writes và conflict resolution của Cosmos DB khác nhau theo mode/tính năng. Test phải dựa trên conflict policy đã cấu hình, session tokens/read region và failover semantics được công bố.

Không giả định một LWW resolver hoặc stored-procedure custom conflict resolver hoạt động giống nhau trong mọi API/model/version.

---

## 32. Một ma trận contract trước khi chạy test

Điền rõ những trường sau cho mỗi collection/table:

~~~yaml
entity: "Wishlist"
key_scope: "tenantId + userId"
replication:
  mode: "multi-region asynchronous"
  regions: ["A", "B"]
  read_modes: ["eventual", "session-if-supported"]
conflict_policy:
  type: "add-wins-set"
  delete_behavior: "observed-remove with causal context"
  duplicate_behavior: "idempotent state merge"
expected_convergence:
  condition: "no new writes, network healed, repair progress"
  target_slo: "measured, not a protocol proof"
business_invariants:
  - "concurrent independent adds are preserved"
  - "removed observed versions do not resurrect"
test_faults:
  - "partition"
  - "reorder"
  - "duplicate"
  - "offline client"
  - "restart"
~~~

Đây là **mẫu tài liệu kiểm thử**, không phải cấu hình chung của MongoDB/Cassandra/DynamoDB/Cosmos DB.

### 32.1. Một entity khác cần contract khác

Với `Inventory`, có thể viết:

~~~yaml
entity: "InventoryAllocation"
invariant:
  - "confirmed quantity never exceeds capacity"
write_authority: "conditional transaction or escrow allocation"
convergence:
  - "replicas eventually expose committed allocation history"
not_acceptable:
  - "LWW drops one confirmed allocation without reconciliation"
~~~

Chính sách của Wishlist không nên sao chép nguyên sang Inventory.

---

## 33. Điều kiện pass/fail cho test hội tụ

### 33.1. PASS

Một test pass khi:

- Các điều kiện môi trường của test được ghi nhận đã thỏa.
- State cuối tương đương theo semantic equality đã định.
- Conflict policy chọn/giữ đúng versions.
- Business invariants đều hợp lệ.
- Không có side effect trùng/lạc theo contract.
- Nếu có SLO, thời gian hội tụ nằm trong ngưỡng thử nghiệm hoặc đạt tỷ lệ thống kê yêu cầu.
- Có đủ telemetry để giải thích vì sao pass.

### 33.2. FAIL_CONVERGENCE

Ví dụ mạng đã phục hồi, repair tiến triển, không có write mới, nhưng A và B mãi giữ hai logical states khác nhau hoặc liên tục đảo giá trị do merge non-deterministic.

### 33.3. FAIL_SEMANTICS

A/B cuối cùng giống nhau nhưng mất một concurrent add mà business contract yêu cầu bảo toàn, hoặc giữ quyền đã bị thu hồi.

### 33.4. FAIL_BUSINESS_INVARIANT

A/B cuối cùng giống nhau nhưng đã xác nhận hai reservation khi capacity=1.

### 33.5. FAIL_SLO

Các replicas cuối cùng hội tụ đúng nhưng p99 thời gian hội tụ vượt mục tiêu vận hành đã công bố.

### 33.6. INCONCLUSIVE

Test environment vẫn partitioned, một replica chết, repair không chạy theo assumptions, source log đã bị xóa ngoài phạm vi setup, hoặc test runner mất dữ liệu history.

**Không gắn nhãn “convergence bug” cho một test không đủ điều kiện quan sát.**

---

## 34. Metrics và telemetry cần thu

| Nhóm | Metric | Mục đích |
|---|---|---|
| Replication | Lag bytes/time, applied sequence | Có truyền kịp không? |
| Conflict | Conflicts per key, sibling counts | Bao nhiêu xung đột phát sinh? |
| Merge | Merge duration/errors, tie-break count | Có tắc hoặc nondeterminism? |
| Repair | Pending repairs, failures, last successful run | Anti-entropy có tiến triển? |
| Tombstone | Tombstone age/count, GC events | Nguy cơ resurrection |
| Metadata | Vector/dot size, actor cardinality | State phình theo thời gian? |
| Availability | Region/node outage duration | Điều kiện hội tụ bị chặn bao lâu? |
| Consistency | RYW/monotonic-read violations | Bảo đảm theo session |
| Correctness | Oversell, duplicate grant, balance mismatch | Business invariant |
| CDC/index | Source vs downstream watermark | Read models có stale? |
| Retry | Attempts per request/event ID | Duplicate side effects |
| Performance | Read/write p99, repair I/O | Tác động foreground |
| Storage | SSTable/segment, compaction backlog | Ảnh hưởng cleanup |
| Convergence | Time-to-converge p50/p95/p99 | SLO thực tế |
| Test | Seed, fault schedule, operation history | Tái hiện và điều tra |

### 34.1. Metrics theo key cohort

Không chỉ lấy trung bình toàn cluster. Chia theo:

- Key nóng/lạnh.
- Tenant.
- Region pair.
- Dữ liệu có/không có tombstone.
- Cỡ document.
- Age của offline client.
- Loại merge policy.
- Retry/repair workload.

### 34.2. Tránh dữ liệu nhạy cảm trong log

Test traces cần IDs và hashes thay vì nội dung cá nhân, bí mật hoặc payment data. Lịch sử dùng để tái hiện nhưng không được tạo thêm rủi ro bảo mật.

---

## 35. Các dấu hiệu test chưa có giá trị kết luận

Các cách làm dưới đây thường tạo “test xanh” giả:

1. Chỉ so **một replica** với cache gần nó.
2. Chỉ test một write không có concurrency.
3. Chỉ chờ 2 giây rồi coi tất cả replica phải bằng nhau.
4. Bỏ qua write outcome `UNKNOWN`.
5. Không test duplicate/reordered replication.
6. Không test restart trong lúc merge.
7. Không test stale replica quay lại **sau** tombstone GC.
8. Không kiểm business invariant.
9. Chỉ so final JSON, bỏ qua causal/tombstone metadata cần thiết.
10. Dùng random seed nhưng không lưu operations history.
11. Test LWW mà lấy real-time wall clock làm expected winner sai semantics.
12. Test MongoDB single-leader như hệ two-primary active-active.
13. Cho B “offline” nhưng thực tế client read luôn qua A.
14. Không kiểm topology/consistency mode của từng read.
15. Kết luận convergence dù network chưa lành.
16. Không xác nhận anti-entropy thực sự chạy.
17. Không kiểm source và read model riêng.
18. Không kiểm transition `delete -> stale rejoin`.
19. Gộp lỗi “SLO hội tụ chậm” với “merge sai”.
20. Không đánh giá effect của message retention và actor GC.
21. Không chừa thời gian cho compaction/repair theo engine.
22. Bật fault injection trên production không được phép.
23. Đánh giá data equality nhưng bỏ qua external side effects.
24. Không bảo đảm test cleanup/rollback giữa các kịch bản.

---

## 36. Runbook phân tích khi replica không hội tụ

### Bước 1 — Xác minh yêu cầu

- Entity và key nào?
- Policy LWW, MV, CRDT hay application merge?
- Business invariant có bị vi phạm?
- SLO hội tụ có áp dụng không?
- Scope region/shard/replica nào?

### Bước 2 — Thu thập state từ nguồn phù hợp

- Đọc các replicas/regions qua đường được phép.
- Ghi version/timestamp/tombstone metadata.
- Ghi read consistency, client session context.
- So canonical logical values.
- Tránh làm thay đổi state ngoài dự định trong lúc điều tra.

### Bước 3 — Kiểm replication path

- Mạng đã lành chưa?
- Lag/checkpoint ở đâu?
- Source log còn đủ không?
- Repair đã chạy và thành công chưa?
- Node có stale membership/routing không?

### Bước 4 — Kiểm conflict resolution

- Comparator/tie-break deterministic?
- Version vectors/dots đúng?
- Duplicate delivery được xử lý lũy đẳng?
- Merge có tính giao hoán/kết hợp theo data model?
- Clock skew hoặc actor churn có liên quan?

### Bước 5 — Kiểm delete/GC

- Tombstone đã bị xóa quá sớm?
- Replica offline bao lâu?
- Có full resync sau expiration window không?
- Có stale snapshot được nạp lại?
- Có TTL/backup restore mang record cũ?

### Bước 6 — Kiểm schema/version

- Các nodes cùng phiên bản merge logic?
- Old clients có thể ghi thiếu causal context?
- Unknown fields có bị drop?
- Có migration/backfill đang chạy?

### Bước 7 — Xác minh tác động nghiệp vụ

- Có oversell/duplicate allocation?
- Có quyền đã revoke bị phục hồi?
- Payment/email/event đã phát trùng?
- Có cần compensation/reconciliation?

### Bước 8 — Phục hồi an toàn

Sử dụng công cụ repair/rebuild/restore **chính thức** của engine và theo quy trình được phê duyệt. Không xóa thủ công tombstones, điều chỉnh timestamps hoặc ép một replica thắng khi chưa biết hậu quả.

### Bước 9 — Chốt và ngăn tái diễn

- Lưu timeline, seed, minimal counterexample.
- Tách root cause transport/merge/metadata/business.
- Bổ sung test regression phù hợp.
- Cập nhật retention/repair schedule, telemetry và policy.
- Kiểm lại toàn bộ key cohort bị ảnh hưởng nếu cần.

---

## 37. Bài tập 1: ACI và thứ tự merge

Có ba state:

~~~text
A = {replicaA: 4}
B = {replicaB: 3}
C = {replicaA: 2, replicaC: 5}
~~~

Dùng G-Counter merge theo max per actor:

1. Tính `merge(A,B)`.
2. Tính `merge(B,A)`.
3. Tính `merge(merge(A,B),C)`.
4. Tính `merge(A,merge(B,C))`.
5. Tính `merge(A,A)`.
6. Giá trị cuối bằng bao nhiêu?
7. Nếu thay `max` bằng `sum`, lỗi nào xảy ra khi B được nhận hai lần?

**Gợi ý:** Kết quả cuối theo max là `{replicaA:4,replicaB:3,replicaC:5}`, giá trị 12. Merge không phụ thuộc thứ tự/delivery duplicate.

---

## 38. Bài tập 2: LWW và lệch đồng hồ

Một record có hai update:

~~~text
Real time:
  A writes status=READY at 10:00:00.
  A gets ACK.
  B writes status=CANCELLED at 10:00:01.

Assigned timestamps:
  A: 10:05:00
  B: 09:59:00
~~~

1. LWW theo timestamp chọn trạng thái nào?
2. Nó có chọn write “sau” theo thời gian thực không?
3. Nếu B không thấy write của A và là concurrent theo causal metadata, policy nào khác có thể phù hợp?
4. Nếu cả hai timestamp giống nhau, cần tie-break nào?
5. Nếu business status không cho chuyển CANCELLED về READY, chọn timestamp lớn nhất có đủ không?
6. Bạn sẽ ghi test oracle khác nhau thế nào cho `LWW register` và `Order state machine`?

**Gợi ý:** So timestamp vật lý chỉ chứng minh winner của một comparator, không chứng minh linearizability.

---

## 39. Bài tập 3: tombstone và replica offline

~~~text
T0: K=v1 trên A/B/C.
T1: C offline.
T2: A/B delete K with tombstone version 9.
T3: Tombstone GC happens.
T4: C returns with K=v1 version 7.
~~~

1. Điều gì có thể khiến K hồi sinh?
2. Vì sao test ngay T2 không đủ?
3. Repair/rejoin nên được kiểm trước hoặc sau tombstone GC theo contract nào?
4. Nếu log retention hết trước khi C quay lại, cần full resync không?
5. Oracle nào kiểm giá trị, oracle nào kiểm metadata?
6. Cách bảo đảm không thay đổi production retention chỉ để tái hiện?

---

## 40. Bài tập 4: một inventory hội tụ nhưng oversell

~~~text
Capacity=2.
Region A offline confirms 2 units.
Region B offline confirms 2 units.
After merge: sold=4 everywhere.
~~~

1. Test hội tụ có pass không?
2. Test business invariant có pass không?
3. PN-Counter merge sai hay policy cấp phát sai?
4. Nếu business bắt buộc availability hai region, mô hình escrow/pre-allocated quotas giúp gì?
5. Nếu không thể bảo vệ uniqueness offline, API nên trả trạng thái nào trước khi có authority?
6. Nếu đã gửi email confirm cả hai bên, compensation cần xử lý gì?

---

## 41. Bài tập 5: xây test harness Java

Hãy bổ sung lớp `GCounter` để:

- Generate N random states với seed cố định.
- Shuffle và merge nhiều thứ tự.
- Insert duplicates vào event/state stream.
- Assert ACI trên các trạng thái hợp lệ.
- Ghi minimal failing seed/trace.
- Từ chối số âm và overflow.
- Test actor ID và empty state.
- Đo kích thước metadata khi N actors tăng.
- Thử crash/restore snapshot trong integration test.
- Phân biệt tests của merge function với tests của network replication.

**Yêu cầu:** không dùng random timestamp không lưu seed làm oracle; kết quả phải tái hiện được.

---

## 42. Bài tập 6: thiết kế ma trận đa vùng

Một ứng dụng có:

~~~text
Region A và Region B.
Wishlist dùng add-wins OR-Set.
Profile nickname dùng LWW register.
Inventory dùng transactional conditional allocation.
Search index nhận CDC eventual.
Clients có thể offline 24 giờ.
~~~

Thiết kế tối thiểu mười test cases, mỗi ca có:

1. Setup/version ban đầu.
2. Writers và operations.
3. Fault schedule.
4. Expected conflict behavior.
5. Convergence oracle.
6. Domain invariant.
7. Read mode/source.
8. Time budget và outcome classification.
9. Telemetry.
10. Cleanup.

Gợi ý: concurrent add, add/remove, clock skew, tied timestamp, delete stale rejoin, offline 24h, duplication, leader failover, conditional inventory race, CDC lag.

---

## 43. Bài tập 7: đánh giá một tuyên bố thiếu chặt chẽ

Nhóm kỹ thuật nói:

> “Hệ đã eventual consistent vì sau 10 giây mọi replica đều có giá trị giống nhau. Vì vậy không còn mất dữ liệu, inventory không oversell, session luôn read-your-writes và search luôn đúng.”

Hãy chỉ ra các kết luận chưa có cơ sở:

- Chỉ một lần read bằng nhau không chứng minh mọi lịch sử.
- Merge có thể chọn winner nhưng bỏ thay đổi hợp lệ.
- LWW không tự giữ real-time order.
- Delete/TTL và stale rejoin chưa được test.
- Business invariant khác convergence.
- Read-your-writes là session guarantee riêng.
- Search/index freshness khác source replication.
- ACK durability qua failover khác convergence.
- Timeout/unknown writes cần xét.
- Repair, log retention và schema evolution có thể tạo lỗi muộn.

Viết lại một phát biểu kiểm thử có phạm vi, ví dụ:

> “Trong staging, với policy X, khi ngừng writes và khôi phục kết nối, các replica A/B/C của nhóm key K đạt trạng thái logic giống nhau trong thời hạn D ở N lần thử. Kết quả này không thay thế kiểm thử bất biến inventory, durability và read-your-writes.”

---

## 44. Checklist thiết kế kiểm thử hội tụ

Trước khi công bố một conflict policy an toàn, xác minh:

- [ ] Entity/key scope và replication topology đã được ghi rõ.
- [ ] Conflict policy có mô tả cụ thể theo field/operation.
- [ ] “Equivalent state” đã được định nghĩa (values/versions/tombstones).
- [ ] Business invariant được kiểm độc lập convergence.
- [ ] Concurrent writes có test cả hai thứ tự delivery.
- [ ] Duplicate/replay được kiểm theo semantics idempotency.
- [ ] Merge function có ACI hoặc thuộc tính đúng của algorithm.
- [ ] Version vector/dot/context được bảo toàn khi cần.
- [ ] Tied timestamps/clock skew đã được thử.
- [ ] Delete vs add concurrent có expected policy rõ.
- [ ] Tombstone GC và stale replica rejoin đã được kiểm.
- [ ] TTL, log retention và offline horizon đã được xét.
- [ ] Crash trong copy/repair/merge không làm mất committed history.
- [ ] Membership migration và node catch-up không bỏ metadata.
- [ ] Read-your-writes/session consistency có test riêng.
- [ ] Search/GSI/cache và source có freshness contract riêng.
- [ ] Multi-region conflict policy được kiểm đúng mode sản phẩm.
- [ ] Schema mixed-version/rolling upgrade có test.
- [ ] Idempotency ledger và external side effects có invariant.
- [ ] Fault injection chỉ chạy trong môi trường được phê duyệt.
- [ ] Test có seed, trace, request IDs và outcome UNKNOWN.
- [ ] Convergence deadline được phân biệt với eventual proof.
- [ ] Có metric repair lag, conflicts, sibling count, business anomalies.
- [ ] Có runbook giải quyết mismatch/tombstone resurrection.
- [ ] Không gọi “PASS” nếu điều kiện môi trường chưa thỏa.

---

## 45. Tổng kết

Một hệ NoSQL phân tán có thể “hội tụ” theo nhiều nghĩa. Điều quan trọng là biết **nó hội tụ tới cái gì, bằng cơ chế nào và dưới những điều kiện nào**.

Những kết luận cần nhớ:

1. **Replication, conflict detection, resolution và convergence là các tầng khác nhau.** Đồng bộ message thành công chưa chứng minh merge đúng.
2. **Giao hoán, kết hợp, lũy đẳng** là các tính chất cốt lõi cho nhiều state-based CRDT; test merge bằng nhiều thứ tự/duplicate giúp phát hiện lỗi.
3. **Một trạng thái cuối giống nhau chưa đủ**: LWW có thể làm mất concurrent update, counter có thể hội tụ về số âm, inventory có thể oversell.
4. **Oracle phải theo chính sách thực**: LWW winner, MV siblings, OR-Set add/remove, GCounter max per actor và domain state machine cần expected results khác nhau.
5. **Clock skew, timestamp tie, delete/tombstone và replica offline lâu** là những tình huống đặc biệt quan trọng; lỗi có thể chỉ xuất hiện sau GC hoặc rejoin.
6. **Anti-entropy/repair là điều kiện tiến triển**, không thể hội tụ nếu thông tin cần thiết bị mất hoặc replication luôn bị chặn.
7. **Phân biệt test hội tụ với test consistency mạnh hơn**: linearizability, RYW, transaction atomicity, durability và business invariants không tự đến từ eventual convergence.
8. **Hệ NoSQL khác nhau có cơ chế khác nhau**: Cassandra regular writes, MongoDB primary replication, DynamoDB global modes, CouchDB revision conflicts, Redis variants và Cosmos DB không nên dùng chung một oracle chưa kiểm chứng.
9. **Test phải tái hiện được** bằng seed, lịch sử invocation/response, fault schedule, version/watermark và telemetry.
10. **Kết quả test phải có phạm vi và giới hạn**: `PASS_CONVERGENCE`, `FAIL_SEMANTICS`, `FAIL_BUSINESS_INVARIANT`, `FAIL_SLO` hoặc `INCONCLUSIVE` rõ ràng.

**Câu cần nhớ: “Kiểm tra hội tụ không chỉ hỏi các replica cuối cùng có giống nhau hay không; còn phải hỏi chúng đã giữ đúng những thay đổi được phép, xử lý xung đột theo quy tắc đã công bố và không vi phạm bất biến nghiệp vụ trong suốt quá trình đồng bộ hay chưa.”**
