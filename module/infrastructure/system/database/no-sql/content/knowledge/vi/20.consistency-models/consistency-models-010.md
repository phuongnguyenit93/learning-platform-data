# Snapshot isolation và những bất thường vẫn có thể xảy ra

Khi một hệ NoSQL cho phép transaction đọc dữ liệu tại **một ảnh chụp nhất quán (consistent snapshot)**, ứng dụng thường dễ nhầm rằng mọi phép kiểm tra trong transaction sẽ luôn dẫn đến một kết quả nghiệp vụ chính xác. Thực tế, **snapshot isolation (SI)** rất hữu ích để tránh một số bất thường đọc, nhưng **không tương đương serializable isolation**. Hai transaction có thể cùng đọc một trạng thái hợp lệ, cập nhật **hai bản ghi khác nhau**, cùng commit và tạo ra một trạng thái **vi phạm bất biến xuyên bản ghi**. Bất thường kinh điển là **write skew**.

Ví dụ một khoa bệnh viện quy định **luôn phải có ít nhất một bác sĩ trực**. Ban đầu A và B đều trực:

~~~text
Doctor A: onCall = true
Doctor B: onCall = true

Transaction T1: đọc A và B, thấy B vẫn trực nên cho A nghỉ.
Transaction T2: đọc A và B, thấy A vẫn trực nên cho B nghỉ.

T1 cập nhật Doctor A = false.
T2 cập nhật Doctor B = false.

Nếu cả hai được commit:
    A = false, B = false

=> Không còn bác sĩ trực.
~~~

Mỗi transaction đã đọc một snapshot hợp lệ. Vì chúng ghi **hai record không trùng nhau**, một cơ chế chỉ phát hiện xung đột write–write trên cùng bản ghi có thể không từ chối transaction nào. Đó là lý do phải hiểu **hợp đồng isolation của sản phẩm** chứ không chỉ dựa vào tên “transaction” hoặc “snapshot”.

Bài học đi từ nguyên lý MVCC, cách hình thành snapshot, những bất thường bị ngăn và những bất thường còn tồn tại, đến các biện pháp bảo vệ invariant trong NoSQL, ví dụ code và phương pháp kiểm thử cạnh tranh.

> **Phạm vi:** SI là một mô hình isolation mang tính lý thuyết với các đặc trưng cụ thể. MongoDB, DynamoDB, Firestore, Cosmos DB, Couchbase, Cassandra/ScyllaDB, Redis và những transactional key–value store có thể dùng các cơ chế rất khác nhau. Một sản phẩm có snapshot read không nhất thiết cung cấp đầy đủ SI theo nghĩa lý thuyết; một sản phẩm khác có thể hỗ trợ isolation mạnh hơn SI. Phiên bản, topology, SDK, API và cấu hình có thể thay đổi bảo đảm. Vì vậy, khi áp dụng thực tế phải đọc đúng tài liệu của hệ đang triển khai.

## 1. Isolation giải quyết vấn đề gì?

Trong hệ thống chỉ có một writer chạy lần lượt, quy tắc “đọc rồi cập nhật” có vẻ đơn giản:

~~~text
READ current state
CHECK business rule
WRITE new state
~~~

Nhưng trong thực tế, nhiều request cùng thực hiện các bước này. Việc đọc và ghi có thể giao nhau:

~~~text
Thời gian       Transaction T1             Transaction T2
-----------------------------------------------------------------
t0              BEGIN
t1              READ A
t2                                          BEGIN
t3                                          READ A
t4              WRITE A
t5                                          WRITE B
t6              COMMIT
t7                                          COMMIT
~~~

**Isolation** định nghĩa những tương tác nào giữa các transaction được phép quan sát hoặc được phép commit. Atomicity chỉ nói một transaction commit toàn bộ hoặc không commit; nó **không tự xác định** các transaction đồng thời có thể tạo ra lịch thực thi như thế nào.

### 1.1. Bốn câu hỏi phải phân biệt

| Câu hỏi | Thuộc tính liên quan | Ví dụ |
|---|---|---|
| Một transaction ghi nhiều document có commit toàn bộ không? | **Atomicity** | Order và Outbox cùng thành công hoặc cùng rollback |
| Hai transaction đồng thời được thấy dữ liệu gì? | **Isolation** | T1 có thấy update chưa commit của T2? |
| Sau ACK, dữ liệu sống sót qua lỗi nào? | **Durability** | Mất node leader sau commit |
| Reader ở các replica thấy phiên bản mới khi nào? | **Replication/read consistency** | Follower còn trả trạng thái cũ |

Không thể suy từ “read consistency mạnh” rằng transaction nhiều bản ghi luôn serializable; cũng không thể suy từ “atomic write một document” rằng mọi bất biến giữa nhiều document được giữ nguyên.

### 1.2. Bất biến (invariant) quan trọng hơn câu khẩu hiệu

Ví dụ:

- Tổng hàng được giữ không vượt tồn kho có thẩm quyền.
- Một khóa username chuẩn hóa chỉ thuộc tối đa một tài khoản.
- Luôn có ít nhất một bác sĩ trực trong một ca.
- Tổng tiền của các dòng Order khớp giá và discount đã chốt.
- Một lần chuyển tiền không tự tạo hoặc làm mất giá trị.
- Một tài khoản không được duyệt hai yêu cầu vượt quota cùng lúc.

Mỗi bất biến cần một **ranh giới kiểm tra–commit** phù hợp. SI giúp đọc một ảnh chụp nhất quán, nhưng một ảnh chụp đúng chưa chắc đủ để bảo vệ một invariant liên quan nhiều record.

## 2. Snapshot isolation là gì?

Trong mô hình SI điển hình, mỗi transaction đọc dữ liệu từ một **snapshot ổn định của những phiên bản đã commit** tại một mốc logic. Các thay đổi chưa commit của transaction khác không xuất hiện trong snapshot. Transaction có thể đọc lại cùng dữ liệu và tiếp tục thấy phiên bản thuộc snapshot cũ, ngay cả khi giao dịch khác đã commit phiên bản mới.

Một hệ hỗ trợ SI thường dùng **multi-version concurrency control (MVCC)** hoặc một cơ chế tương đương. Thay vì chỉ có một bản sao hiện tại, storage engine có thể giữ nhiều phiên bản logic của một record trong khoảng thời gian cần thiết để các transaction đọc cũ.

~~~mermaid
flowchart LR
    V1["K = 10\ncommit version 100"] --> V2["K = 15\ncommit version 110"]
    V2 --> V3["K = 20\ncommit version 120"]
    S1["Snapshot S=105"] -. "thấy K=10" .-> V1
    S2["Snapshot S=115"] -. "thấy K=15" .-> V2
    S3["Snapshot S=125"] -. "thấy K=20" .-> V3
~~~

Mốc snapshot là khái niệm logic, không nhất thiết là một timestamp wall-clock có thể so sánh trực tiếp giữa mọi node.

### 2.1. Cách chọn phiên bản hiển thị

Một biểu diễn đơn giản:

~~~text
Visible(record, snapshot):
    chọn phiên bản hợp lệ mới nhất
    đã commit không muộn hơn mốc snapshot,
    theo quy tắc transaction visibility của engine.
~~~

Đây chỉ là trực giác. Engine thật còn xử lý transaction chưa commit, commit timestamps, delete markers, version chains, shards, causal/replication state và cách snapshot được tạo. Không xây logic business dựa trên việc tự đoán commit timestamp của sản phẩm.

### 2.2. Read-your-own-writes

Thông thường, transaction có thể thấy **các thay đổi do chính nó tạo ra** trong phạm vi semantics được API định nghĩa, dù snapshot ngoài transaction vẫn đại diện cho phiên bản cũ.

~~~text
T1 BEGIN at snapshot S=100
T1 READ Order.status -> PENDING
T1 UPDATE Order.status -> CONFIRMED
T1 READ Order.status -> CONFIRMED   (nếu API hỗ trợ đọc lại own writes)
~~~

Chi tiết này phải kiểm tra theo API. Một số SDK giới hạn thứ tự read/write hoặc query visibility trong transaction, nên không lấy pseudocode trên làm cam kết cho mọi sản phẩm.

### 2.3. Snapshot không phải sao chép vật lý toàn database

Không cần copy toàn bộ data file mỗi khi bắt đầu transaction. MVCC thường chọn các phiên bản đã có và giữ chúng đủ lâu. Những long-running snapshot có thể làm chậm thu hồi phiên bản cũ, tăng áp lực storage, compaction hoặc garbage collection tùy engine.

### 2.4. Snapshot nhất quán khác snapshot mới nhất

Một transaction bắt đầu ở mốc S có thể tiếp tục đọc dữ liệu của S dù lúc này một writer khác đã commit S+1. Đọc **ổn định** không đồng nghĩa đọc **mới nhất**.

## 3. Một ví dụ đơn giản về phiên bản và thời điểm

Giả sử Inventory ban đầu:

~~~text
Available(SKU-A) = 10
~~~

Timeline:

~~~text
t0: Transaction T1 BEGIN, snapshot = S100
t1: T1 READ Available -> 10
t2: Transaction T2 BEGIN
t3: T2 UPDATE Available = 8
t4: T2 COMMIT, version = S101
t5: T1 READ Available -> 10 (theo snapshot S100)
t6: T1 COMMIT/END
t7: New Transaction T3 READ Available -> 8
~~~

T1 nhìn thấy một snapshot ổn định. Đó là lợi ích lớn của SI: nhiều báo cáo hoặc phép tính nhiều bước tránh được việc cùng một record nhảy giữa các giá trị giữa transaction.

Nhưng nếu T1 quyết định dựa trên `Available = 10` rồi ghi một **record khác** mà không kiểm tra invariant lúc commit, T1 có thể đưa ra quyết định không còn phù hợp với trạng thái mới của Inventory.

## 4. SI thường ngăn được những bất thường nào?

Trong mô hình SI chuẩn có snapshot nhất quán và quy tắc chống xung đột write–write (thường gọi là first-committer-wins hoặc first-updater-wins), có thể phân biệt như sau:

| Hiện tượng | Với SI chuẩn | Giải thích |
|---|---|---|
| **Dirty read** | Được ngăn | Không đọc dữ liệu chưa commit của transaction khác |
| **Non-repeatable read** | Được ngăn trong cùng snapshot | Đọc lại record vẫn thấy cùng phiên bản snapshot |
| **Phantom xuất hiện khi đọc lại cùng truy vấn** | Được ngăn trong cùng snapshot nhất quán | Query lặp lại nhìn cùng tập phiên bản thuộc snapshot |
| **Dirty write** | Được ngăn | Không cho ghi đè thay đổi chưa commit trái semantics |
| **Lost update do hai transaction cùng ghi một record** | Thường được ngăn trong SI chuẩn nhờ write conflict detection | Một transaction phải abort khi hai writer cạnh tranh cùng record |
| **Write skew trên hai record khác nhau** | **Vẫn có thể xảy ra** | Hai transaction đọc invariant chung nhưng ghi hai record riêng |
| **Predicate/constraint anomaly** | **Vẫn có thể xảy ra** | Mỗi transaction tạo record khác nhau sau khi cùng kiểm tra một điều kiện tập hợp |
| **Serializability cho mọi history** | **Không được bảo đảm chỉ bởi SI** | Có thể có chu trình phụ thuộc giữa các transaction |

**Lưu ý:** Những hàng trên mô tả **SI theo nghĩa chuẩn**, không phải mọi tính năng có chữ “snapshot”. Một số database chỉ cung cấp snapshot cho read hoặc có phạm vi/semantics yếu hơn. Một số hệ hỗ trợ serializable, qua đó loại thêm bất thường. Phải tra điều kiện thực tế.

### 4.1. Dirty read

T2 sửa giá từ 100 thành 80 nhưng chưa commit. Nếu T1 nhìn thấy 80, sau đó T2 rollback, T1 đã dùng một giá không bao giờ trở thành trạng thái committed. SI tránh kiểu đọc này qua visibility của snapshot.

### 4.2. Non-repeatable read

T1 đọc `Status = PENDING`; T2 commit đổi thành `CONFIRMED`; T1 đọc lại vẫn thấy `PENDING` từ snapshot ban đầu. Đọc lặp trong cùng snapshot có tính ổn định.

### 4.3. Phantom: cần phân biệt hai ý nghĩa

Một truy vấn:

~~~text
SELECT all reservations WHERE eventId = E AND status = ACTIVE
~~~

Trong một **snapshot đúng nghĩa**, nếu T2 insert thêm Reservation mới sau mốc snapshot của T1, T1 thường không thấy record đó khi lặp lại cùng truy vấn; vì thế **không có phantom do đọc lặp trong cùng snapshot**.

Nhưng **hai transaction có thể cùng đọc một predicate**, rồi insert **hai bản ghi khác nhau** khiến invariant dựa trên predicate bị sai sau khi cả hai commit. Đây là một **predicate anomaly/write skew**, không mâu thuẫn với việc mỗi transaction đọc snapshot ổn định.

### 4.4. Lost update cần nói chính xác

Nhiều trình bày đơn giản viết “SI ngăn lost update”. Điều này đúng với **SI chuẩn có first-committer-wins trên cùng item được ghi**. Nhưng nếu ứng dụng đọc ngoài transaction, ghi không điều kiện trong một transaction khác, dùng API có contract yếu hơn hoặc writer khác bỏ qua cơ chế version, lost update ở tầng nghiệp vụ vẫn có thể xảy ra.

~~~text
Request A: read Order v7 outside transaction
Request B: update Order -> v8
Request A: replace whole Order using old document v7
~~~

Nếu A không gửi condition expectedVersion, chỉ vì database *có hỗ trợ SI* ở một API khác không có nghĩa thao tác replace của A được bảo vệ.

## 5. Write skew: bất thường tiêu biểu của SI

Quay lại bài toán bác sĩ. Ban đầu:

~~~text
Doctor A: onCall = true
Doctor B: onCall = true

Invariant:
    COUNT(Doctor WHERE onCall = true) >= 1
~~~

Hai transaction đồng thời:

~~~text
T1 snapshot S0: READ A=true, B=true
T2 snapshot S0: READ A=true, B=true

T1: thấy B vẫn trực, UPDATE A.onCall=false
T2: thấy A vẫn trực, UPDATE B.onCall=false

T1 COMMIT.
T2 COMMIT.

Final:
    A=false, B=false
    COUNT(onCall=true)=0
~~~

### 5.1. Lịch thực thi

| Thời điểm | Transaction T1 | Transaction T2 |
|---|---|---|
| t0 | BEGIN, snapshot S0 | |
| t1 | READ A=true, B=true | |
| t2 | | BEGIN, snapshot S0 |
| t3 | | READ A=true, B=true |
| t4 | UPDATE A=false | |
| t5 | | UPDATE B=false |
| t6 | COMMIT | |
| t7 | | COMMIT |
| t8 | \multicolumn{2}{c}{A=false, B=false: invariant bị phá} |

T1 và T2 **không cùng ghi một record**. Nếu cơ chế SI chỉ từ chối transaction khi **write sets giao nhau**, cả hai có thể commit. Mỗi transaction đã đưa ra quyết định hợp lý trong snapshot riêng nhưng hai quyết định kết hợp lại sai.

### 5.2. Tại sao không thể sắp thành thứ tự tuần tự?

Thử sắp T1 trước T2:

~~~text
T1 commit A=false.
T2 nếu chạy sau T1 theo một thứ tự tuần tự thật,
T2 phải đọc A=false và không được cho B nghỉ.
~~~

Thử sắp T2 trước T1:

~~~text
T2 commit B=false.
T1 chạy sau T2 phải đọc B=false
và không được cho A nghỉ.
~~~

Cả hai thứ tự đều không tương thích với các lần đọc đã xảy ra. Vì vậy history có thể hợp lệ dưới SI nhưng **không serializable**.

### 5.3. Vì sao đây không phải atomicity failure?

Giả sử mỗi transaction chỉ ghi một doctor:

~~~text
T1 ghi Doctor A hoàn toàn hoặc không.
T2 ghi Doctor B hoàn toàn hoặc không.
~~~

Atomicity của T1 và T2 có thể hoàn toàn đúng. Lỗi nằm ở việc hai transaction **ra quyết định dựa trên một bất biến xuyên hai record**, nhưng isolation không đủ để ngăn lịch thực thi nguy hiểm.

## 6. Nhìn write skew dưới góc độ phụ thuộc đọc–ghi

Một công cụ tư duy hữu ích là **serialization graph**. Mỗi transaction là một đỉnh; các cạnh diễn tả quan hệ phụ thuộc giữa chúng.

Trong ví dụ bác sĩ:

- T1 **đọc B=true**, nhưng T2 **ghi B=false** sau snapshot của T1. Điều này tạo một quan hệ phụ thuộc đọc–ghi ngược chiều (read–write anti-dependency) T1 → T2.
- T2 **đọc A=true**, nhưng T1 **ghi A=false** sau snapshot của T2, tạo anti-dependency T2 → T1.

~~~mermaid
flowchart LR
    T1["T1: đọc B, ghi A"] -->|"rw anti-dependency trên B"| T2["T2: đọc A, ghi B"]
    T2 -->|"rw anti-dependency trên A"| T1
~~~

Có **chu trình** T1 → T2 → T1 nên không thể tìm một thứ tự serial tương thích. Một hệ chỉ so sánh các **write sets** sẽ không thấy giao nhau: T1 ghi A còn T2 ghi B.

### 6.1. Cạnh đọc–ghi là gì?

Trong lập luận về serializability, một transaction đọc phiên bản cũ trong khi transaction khác tạo phiên bản mới của cùng item/predicate có thể tạo một ràng buộc thứ tự. Khi nhiều ràng buộc xung đột tạo chu trình, history không serializable.

Không cần tự cài serialization graph cho một ứng dụng thông thường, nhưng hiểu nó giúp thấy vì sao **“không có write conflict” không đủ kết luận “không có xung đột nghiệp vụ”**.

### 6.2. Serializable Snapshot Isolation (SSI)

Một số engine có cơ chế mạnh hơn SI, thường được mô tả theo hướng **Serializable Snapshot Isolation** hoặc các kỹ thuật phát hiện lịch nguy hiểm. Ý tưởng là theo dõi những phụ thuộc đọc–ghi có thể dẫn đến non-serializable history và abort transaction thích hợp.

Không được suy rằng một hệ có MVCC hoặc hỗ trợ snapshot reads **tự động có SSI**. Mức serializable phải được tài liệu hóa và bật đúng theo API/configuration.

### 6.3. Serializable có thể từ chối một transaction

Kết quả mong đợi dưới cơ chế serializable phù hợp không phải “cả T1 và T2 đều commit bằng cách nào đó”. DB có thể abort một transaction. Application cần retry **toàn đơn vị công việc**; khi đọc lại snapshot mới, nó sẽ thấy người kia đã nghỉ và từ chối nghỉ thêm.

## 7. Bất thường trên tập bản ghi: tạo username trùng

Giả sử một hệ lưu mỗi tài khoản dưới một khóa ngẫu nhiên:

~~~text
User(userId=U1, username=an123)
User(userId=U2, username=an123)
~~~

Nghiệp vụ yêu cầu `username` duy nhất. Hai client cùng:

~~~text
T1: query "username = an123" -> 0 rows
T2: query "username = an123" -> 0 rows

T1: INSERT User(U1, an123)
T2: INSERT User(U2, an123)

T1 COMMIT
T2 COMMIT
~~~

Nếu không có unique constraint, conditional key hoặc serializable predicate protection, **hai insert ghi hai record khác nhau** có thể cùng thành công. Mỗi transaction đọc một snapshot không có `an123`; sau hai commit, uniqueness bị phá.

### 7.1. Đây có phải phantom read không?

Không nhất thiết. Trong từng transaction, truy vấn lặp lại từ cùng snapshot vẫn có thể trả 0 record. Vấn đề là **predicate “không tồn tại username” không được bảo vệ đến lúc commit đối với các writer tạo record mới**.

### 7.2. Thiết kế một key có thẩm quyền

Một cách thường hiệu quả trong NoSQL là dùng canonical username làm **khóa duy nhất có thể cạnh tranh**:

~~~text
UsernameRegistry:
    key = (tenantId, canonicalUsername)
    value = userId

Conditional create:
    INSERT key only if absent
~~~

Hai request cùng `canonicalUsername` phải cùng cạnh tranh trên một key. Nếu conditional create có atomicity đúng phạm vi, chỉ một request thành công.

Nếu cần tạo User profile và registry atomically, phải kiểm tra transaction scope hoặc thiết kế workflow có trạng thái reservation để tránh registry trỏ đến User chưa tồn tại.

### 7.3. Chuẩn hóa tên trước khi bảo vệ uniqueness

Nếu `An123`, `an123` và ký tự Unicode tương đương bị coi là cùng username theo business, cần quy tắc canonicalization nhất quán trước khi dùng key. Transaction mạnh không sửa được một **định nghĩa key không nhất quán**.

## 8. Bất thường quota: mỗi transaction ghi một reservation khác nhau

Một hệ quản lý phòng họp cho phép tối đa **10 chỗ**:

~~~text
Room R1:
    capacity = 10

Reservations hiện tại:
    R-1 quantity = 5
~~~

Hai người cùng yêu cầu giữ 4 chỗ:

~~~text
T1 snapshot:
    SUM(activeReservation.quantity) = 5
    5 + 4 <= 10 => được
    INSERT Reservation(R-2, qty=4)

T2 snapshot:
    SUM(activeReservation.quantity) = 5
    5 + 4 <= 10 => được
    INSERT Reservation(R-3, qty=4)

Hai bản ghi khác nhau cùng được commit.
Final SUM = 13 > 10.
~~~

Mỗi snapshot có tổng 5 hợp lệ, nhưng invariant dựa trên tổng của **một tập bản ghi động** bị phá.

### 8.1. Cách đúng không phải chỉ “query kỹ hơn”

Query lại nhiều lần trong cùng snapshot vẫn thấy tổng 5. Muốn bảo vệ invariant, cần một cơ chế commit-time:

- Một **counter/quota owner** được giảm có điều kiện atomically.
- Một transaction có **serializable isolation** đúng phạm vi.
- Một **guard record** làm điểm tranh chấp chung.
- Pre-allocated quota theo shard có bảo đảm tổng quota không vượt 10.

### 8.2. Không dùng read model trễ làm nguồn quyết định

Nếu tổng reservation lấy từ search index hoặc projection cập nhật bất đồng bộ, ngay cả một transaction có SI trên nguồn Order cũng không làm query index trở nên nhất quán. Bất biến quota phải được kiểm tra tại **nguồn có thẩm quyền và ranh giới commit phù hợp**.

## 9. SI, read committed, repeatable read và serializable khác nhau thế nào?

Các tên isolation quen thuộc có thể được triển khai khác nhau giữa sản phẩm. Bảng sau là **so sánh định hướng**, không thay thế contract DB.

| Mô hình | Cách nhìn dữ liệu | Giới hạn cần nhớ |
|---|---|---|
| **Read uncommitted** | Có thể thấy dữ liệu chưa commit trong một số hệ | Dirty read và nhiều anomaly |
| **Read committed** | Thường chỉ đọc giá trị committed; các lần đọc có thể dùng snapshot khác | Non-repeatable read/read skew có thể xảy ra |
| **Repeatable read** | Có quy tắc giữ ổn định lần đọc lặp, semantics tùy engine | Không được suy tự động là SI hoặc serializable |
| **Snapshot isolation** | Đọc snapshot nhất quán; SI chuẩn ngăn concurrent write–write conflict | Write skew và predicate anomalies còn có thể xảy ra |
| **Serializable** | Kết quả tương đương một thứ tự tuần tự của các transaction | Không mặc nhiên bảo đảm thứ tự real-time |
| **Strict serializable** | Serializable và tôn trọng thứ tự real-time của transaction hoàn tất | Thường đòi cơ chế phối hợp/đọc–ghi mạnh hơn |

### 9.1. Snapshot isolation không đồng nghĩa serializable

SI cho phép nhiều transaction đọc ảnh chụp cũ đồng thời, chỉ phải xung đột khi cập nhật cùng record theo quy tắc write conflict. Serializable phải loại những history **không thể quy về thứ tự tuần tự**, kể cả khi writes nằm trên record khác nhau.

### 9.2. Serializable không đồng nghĩa linearizability của mọi API

**Linearizability** thường nói về hành vi của từng thao tác trên đối tượng theo thứ tự real-time. **Serializable** nói về lịch tương đương tuần tự của transaction; nó không nhất thiết giữ thứ tự real-time. **Strict serializability** kết hợp yêu cầu serializability với ràng buộc real-time.

Một hệ có transaction serializable trên tập item nhưng read API khác qua replica yếu hơn; không thể gộp thành câu “mọi truy cập đều linearizable”.

### 9.3. Snapshot ổn định có thể vẫn cũ

Một transaction mở snapshot S rồi được giữ lâu có thể đọc state cũ trong nhiều giây/phút dù writer khác commit. Điều này phù hợp với snapshot consistency. Nếu UI/checkout cần xác nhận trạng thái **ngay tại thời điểm quyết định**, phải sử dụng condition/transaction đủ mạnh, không chỉ một snapshot đọc cũ.

### 9.4. “Strong consistency” không phải đồng nghĩa transaction serializable

Một database có thể cung cấp strong reads trên một item nhưng không transaction nhiều item. Ngược lại, một transaction SI trên nhiều item có thể đọc từ snapshot cũ. Cần tách **freshness/replica consistency** và **isolation của concurrent transactions**.

## 10. Những bất thường vẫn có thể xuất hiện do dùng sai phạm vi

Một số lỗi thường bị gọi nhầm là “SI không tốt” thực ra xảy ra vì application **đã không đặt mọi thao tác trong cùng transaction scope**.

### 10.1. Đọc ngoài transaction, ghi bên trong

~~~text
read Order v7 outside transaction
other writer commits Order v8
begin transaction
replace Order using full object v7
commit
~~~

Nếu lệnh không kiểm tra version/predicate, có thể xảy ra lost update. Một tính năng snapshot ở transaction khác không tự bảo vệ lần đọc ngoài transaction.

### 10.2. Transaction chỉ bao một partition

Nếu Order và Inventory thuộc hai logical partition trong hệ chỉ hỗ trợ transaction cùng partition, hai lần ghi không có chung atomicity/isolation. Application không được gọi một function tên `saveTransactional` rồi coi đó là một transaction thực.

### 10.3. Đọc dữ liệu từ cache/projection

Một read model có độ trễ có thể trả số tồn cũ. Dù transaction ghi Order được bảo vệ bằng SI, **quyết định trừ stock** vẫn sai nếu nguồn dữ liệu để quyết định không ở trong hợp đồng transaction.

### 10.4. Writer khác bỏ qua version policy

Nếu background job cập nhật Doctor.onCall mà không cập nhật guard/version như application chính, invariant có thể bị phá dù code của một endpoint dùng transaction đúng.

### 10.5. Multi-region writer

Hai region có thể cùng chấp nhận thao tác dựa trên snapshot/counter cục bộ rồi đồng bộ sau. Nếu không có transaction/coordination xuyên region đủ mạnh, hợp đồng SI cục bộ không chứng minh invariant toàn cầu được bảo vệ.

## 11. Thiết kế chống write skew: đặt invariant vào một bản ghi

Đơn giản nhất khi khả thi là đưa dữ liệu cần thay đổi atomically vào **cùng một aggregate/document** có kích thước hợp lý.

Ví dụ thay vì hai doctor riêng làm nguồn quyết định, một record Ward có thể chứa danh sách ca trực nhỏ, bounded:

~~~json
{
  "_id": "ward-A",
  "onCallDoctorIds": ["A", "B"],
  "version": 7
}
~~~

Một lệnh kết thúc ca có điều kiện:

~~~text
Remove doctor A from Ward.onCallDoctorIds
IF doctor A is present AND numberOfOnCallDoctors >= 2
~~~

Nếu DB hỗ trợ atomic conditional update một document theo những predicate đó, hai request cùng bỏ A và B phải cạnh tranh trên **cùng record Ward**, thay vì hai record Doctor không giao nhau.

### 11.1. Lợi ích

- Bất biến được kiểm tra trên một nguồn state cục bộ.
- Không cần coordination nhiều record nếu mọi thông tin quyết định nằm trong document.
- Dễ bảo vệ bằng CAS/version hoặc atomic conditional update.

### 11.2. Giới hạn

- Document có giới hạn kích thước và mức tăng trưởng.
- Hot document có thể tăng contention khi ghi rất nhiều.
- Nếu dữ liệu con có vòng đời hoặc quyền riêng khác, nhúng có thể không phù hợp.
- Nếu Doctor records khác vẫn là nguồn thật, phải đồng bộ chúng trong cùng transaction hoặc quy định Ward là source of truth.

Không nhúng một danh sách vô hạn chỉ để tránh transaction. Thiết kế aggregate phải đáp ứng **đường đọc/ghi và tăng trưởng thực tế**.

## 12. Thiết kế chống write skew: guard record làm điểm xung đột

Nếu không thể gộp toàn bộ dữ liệu, có thể tạo một **guard record** đại diện invariant chung.

~~~text
WardGuard(wardId = ward-A):
    onCallCount = 2
    version = 7

Doctor A:
    onCall = true

Doctor B:
    onCall = true
~~~

Mỗi transaction cho một doctor nghỉ phải:

1. Kiểm tra doctor đang onCall.
2. Cập nhật WardGuard với **condition onCallCount > 1**, giảm count và đổi version trong thao tác nguyên tử.
3. Cập nhật Doctor.onCall=false.
4. Commit hai thay đổi trong **cùng transaction thật sự**, hoặc dùng một thiết kế khác có guarantee phù hợp.

Hai transaction giờ cùng ghi WardGuard:

~~~text
T1: update WardGuard (2 -> 1), Doctor A -> false
T2: update WardGuard (2 -> 1), Doctor B -> false
~~~

Nếu transaction có cơ chế phát hiện write–write conflict trên WardGuard, một transaction phải được từ chối/abort. Sau retry, count đã là 1 nên request nghỉ tiếp sẽ bị từ chối theo business rule.

### 12.1. Vì sao guard giúp?

Guard biến bất biến xuyên nhiều bản ghi thành **một điểm ghi có tranh chấp trực tiếp**, mà SI chuẩn có thể phát hiện qua write–write conflict. Không còn chỉ hai cạnh read–write gián tiếp.

### 12.2. Guard phải được cập nhật bởi mọi writer

Nếu admin tool sửa Doctor.onCall trực tiếp mà không sửa WardGuard, count sẽ sai. Guard không có giá trị nếu chỉ một số code path tuân thủ. Cần xác định WardGuard là nguồn có thẩm quyền hoặc bảo đảm cập nhật cùng transaction trên mọi lệnh liên quan.

### 12.3. Guard không giải quyết transaction scope không đủ

Nếu WardGuard và Doctor thuộc hai partition nhưng hệ không có transaction xuyên partition, ứng dụng có thể giảm count thành công rồi fail khi sửa Doctor. Cần lựa chọn partition key khác, dùng một aggregate, transaction đủ mạnh hoặc workflow có khả năng đối soát.

### 12.4. Guard có thể thành hot key

Một bệnh viện lớn có hàng nghìn bác sĩ cùng đổi ca có thể khiến WardGuard bị tranh chấp. Cần đo throughput, conflict rate và khả năng chia invariant theo ward/shift nếu phù hợp; không chia ngẫu nhiên rồi phá ràng buộc chung.

## 13. Ví dụ MongoDB: guard update cùng transaction

Ví dụ MongoDB dưới đây tập trung vào nguyên lý **mọi transaction cùng sửa guard record**, biến write skew thành write conflict hoặc business precondition failure.

Giả sử ba collection:

~~~text
wards:
  { _id: "ward-A", onCallCount: 2, version: 7 }

doctors:
  { _id: "doc-A", wardId: "ward-A", onCall: true }
  { _id: "doc-B", wardId: "ward-A", onCall: true }

outbox:
  { _id: "doctor-offcall:command-001", ... }
~~~

Mẫu JavaScript với MongoDB driver:

~~~javascript
async function endDoctorShift(
  mongoClient, db, wardId, doctorId, commandId
) {
  const session = mongoClient.startSession();
  try {
    return await session.withTransaction(async () => {
      const doctors = db.collection("doctors");
      const wards = db.collection("wards");
      const outbox = db.collection("outbox");

      const doctor = await doctors.findOne(
        { _id: doctorId, wardId, onCall: true },
        { session }
      );
      if (!doctor) {
        throw new Error("DOCTOR_NOT_ON_CALL");
      }

      // Mọi giao dịch phải cạnh tranh trên cùng WardGuard.
      const guardResult = await wards.updateOne(
        {
          _id: wardId,
          onCallCount: { $gt: 1 }
        },
        {
          $inc: { onCallCount: -1, version: 1 }
        },
        { session }
      );
      if (guardResult.matchedCount !== 1) {
        throw new Error("LAST_DOCTOR_MUST_STAY");
      }

      const doctorResult = await doctors.updateOne(
        { _id: doctorId, wardId, onCall: true },
        { $set: { onCall: false } },
        { session }
      );
      if (doctorResult.matchedCount !== 1) {
        throw new Error("DOCTOR_STATE_CHANGED");
      }

      await outbox.insertOne(
        {
          _id: "doctor-offcall:" + commandId,
          type: "DoctorOffCall",
          wardId, doctorId
        },
        { session }
      );
      return { doctorId, state: "OFF_CALL" };
    });
  } finally {
    await session.endSession();
  }
}
~~~

Đây là **mã minh họa cơ chế**, không phải production-ready. Cần còn những việc:

- Xác nhận MongoDB deployment hỗ trợ transaction và cấu hình read/write concern đúng.
- Cung cấp tenant scope, authorization và unique indexes.
- Phân biệt business rejection, write conflict, timeout và unknown commit outcome.
- Thiết kế idempotency cho cùng `commandId`; retry request sau commit không được thực hiện thao tác mới.
- Không gửi email/payment trong callback vì driver có thể retry transaction.
- Mọi writer khác phải giữ WardGuard và Doctor đồng bộ.
- Xem giới hạn transaction về thời gian/kích thước, và lưu sự kiện trong cùng atomic boundary.

### 13.1. Tại sao không chỉ dùng read snapshot?

Nếu hai transaction chỉ update Doctor A và Doctor B, write sets rời nhau. Khi cùng update WardGuard, chúng giao nhau, nên cơ chế write conflict của transaction có một record để điều phối.

### 13.2. Nếu transaction bị abort

Không chỉ retry `updateOne(Doctor)`. Phải **chạy lại toàn transaction callback**: đọc Doctor, kiểm tra WardGuard, cập nhật và ghi Outbox trong một attempt mới theo documented SDK retry semantics.

### 13.3. Nếu commit result UNKNOWN

Client không được mặc định transaction abort. Tra commandId tại nguồn hoặc dùng cơ chế retry commit của driver theo tài liệu. Một lệnh business được gửi lại phải không tạo thêm event hoặc giảm count lần nữa.

## 14. Ví dụ một single-document conditional update

Nếu Ward là **nguồn có thẩm quyền duy nhất** về ca trực, có thể thiết kế atomic update ngay một document thay vì transaction hai collection.

Một schema với count/array bounded:

~~~json
{
  "_id": "ward-A",
  "onCallCount": 2,
  "onCallDoctorIds": ["A", "B"],
  "version": 7
}
~~~

Trong MongoDB, một mẫu filter và update để bỏ A:

~~~javascript
const result = await db.collection("wards").updateOne(
  {
    _id: "ward-A",
    onCallCount: { $gt: 1 },
    onCallDoctorIds: "A"
  },
  {
    $pull: { onCallDoctorIds: "A" },
    $inc: { onCallCount: -1, version: 1 }
  }
);

if (result.matchedCount !== 1) {
  // Doctor không trực, ward không tồn tại,
  // hoặc không còn đủ người để kết thúc ca.
}
~~~

Điều kiện và thay đổi trong **một document** được engine thực hiện theo atomicity của thao tác update. Tuy nhiên cần bảo đảm:

- `onCallCount` luôn bằng số phần tử hợp lệ trong `onCallDoctorIds` qua mọi writer.
- Không có phần tử trùng hoặc quá lớn; cấu trúc bounded.
- Toàn bộ API đọc/ghi trạng thái ca trực dựa vào cùng nguồn.
- Điều kiện/semantics array và index phù hợp với schema.

Nếu hệ muốn Doctor profile ở collection khác là nguồn thực, transaction với guard/doctor vẫn cần hoặc phải chấp nhận eventual projection được thiết kế rõ.

## 15. Serializable isolation: phương án bảo vệ tổng quát hơn

Nếu engine cung cấp **serializable transactions** đúng phạm vi, một lịch write skew như ví dụ bác sĩ cần bị ngăn: có thể một transaction commit, transaction kia bị abort vì serialization conflict.

### 15.1. Không phải mọi lỗi dưới serializable đều là lỗi hệ thống

Một serialization failure có thể là hành vi **đúng** để giữ invariant. Ứng dụng cần:

~~~text
BEGIN new transaction
READ current A/B state
VALIDATE at least one doctor remains
WRITE candidate changes
COMMIT

If documented retryable serialization abort:
    retry entire unit of work with new reads
~~~

Không retry một lệnh update từ snapshot cũ.

### 15.2. Serializable phải được dùng thật

Nếu chỉ đoạn query của Order dùng transaction serializable nhưng Inventory nằm ở service khác, không thể dựa vào isolation của Order để bảo vệ Inventory. Transaction scope cần **bao trùm dữ liệu của invariant**.

### 15.3. Chi phí và contention

Serializable có thể tăng conflict/abort rate, tracking read/predicate ranges hoặc coordination so với SI. Với hot key hay transaction kéo dài, latency có thể tăng. Nhưng **chọn isolation yếu để tăng throughput** khi làm sai nghiệp vụ không phải tối ưu hợp lệ.

### 15.4. SSI khác lock toàn bộ database

Một số cơ chế serializable dùng MVCC và theo dõi conflict thay vì khóa mọi bản ghi cho toàn transaction. Do đó không thể quy “serializable” luôn đồng nghĩa mọi read khóa dữ liệu. Phải đọc cách sản phẩm thực hiện và benchmark.

## 16. Unique key, quota và conditional write thay vì transaction lớn

Không phải invariant nào cũng cần serializable transaction nhiều bản ghi.

| Invariant | Hướng thiết kế thường phù hợp | Điều cần bảo vệ |
|---|---|---|
| Username duy nhất | Conditional create trên canonicalUsername key | Một writer thắng trên key chung |
| Tồn kho không âm | Atomic decrement có condition `available >= qty` | Check và trừ trên cùng nguồn |
| Một ghế chỉ một Booking active | Atomic seat reservation key hoặc unique registry | Không cấp cùng seat hai lần |
| Ít nhất một bác sĩ trực | Single Ward document hoặc WardGuard + transaction | Mọi lệnh cùng cạnh tranh trên invariant |
| Tổng quota nhiều reservation | Central quota counter/guard hoặc serializable | Không hai insert rời nhau cùng vượt quota |
| Chuyển tiền A→B | Transaction đúng phạm vi/ledger protocol | Không commit nửa transfer |
| Order + Outbox | Transaction chung atomic boundary | Không mất event intent khi Order commit |

### 16.1. Conditional decrement

Một thao tác minh họa:

~~~text
UPDATE Inventory(SKU-A)
IF available >= requested
THEN available = available - requested
~~~

Nếu DB kiểm tra predicate và ghi nguyên tử trên item nguồn, hai request đồng thời không thể cùng vượt tồn theo cùng boundary.

**Nhưng:** nếu một client timeout sau khi thao tác đã commit, retry có thể trừ lần thứ hai. Cần **reservationId/idempotency** để chống lặp ý định, không chỉ atomicity.

### 16.2. Dùng unique key không được quên user profile

Đặt username registry và User profile ở hai item có thể gặp trạng thái registry đã tạo nhưng profile chưa tạo. Khi không có transaction chung, cần workflow reservation có trạng thái, TTL/deadline và đối soát an toàn.

### 16.3. Predicate read ngoài transaction vẫn nguy hiểm

Ứng dụng có thể kiểm tra sớm `available >= qty` để trả UX nhanh, nhưng **quyết định cuối** phải được xác minh lại tại atomic write hoặc transaction đủ mạnh. Check sơ bộ không thay thế commit-time precondition.

## 17. Snapshot isolation và event-driven NoSQL

Một hệ dùng SI để cập nhật Order nhưng các read model lại theo event bất đồng bộ:

~~~mermaid
flowchart LR
    TX["Order transaction"] --> SRC["Orders source of truth"]
    TX --> OUT["Outbox trong cùng transaction"]
    OUT --> BUS["Message broker"]
    BUS --> SEARCH["Search index"]
    BUS --> ANALYTICS["Analytics projection"]
~~~

### 17.1. Transaction source không bảo đảm projection cập nhật tức thì

Ngay sau commit, search index có thể còn trạng thái cũ. Điều này không chứng minh transaction source mất atomicity hoặc vi phạm SI.

### 17.2. Một reader ghép nhiều nguồn có thể thấy read skew

Ứng dụng đọc Order từ primary nhưng giá/tồn từ cache hay replica có thời gian cập nhật khác. Những giá trị đó có thể đến từ các mốc không cùng snapshot. SI **trong một transaction DB** không tự tạo một **consistent snapshot xuyên nhiều hệ**.

### 17.3. Event order và idempotency

Outbox event v8 có thể đến sau v9. Consumer cần so sánh version/order hoặc có quy tắc dedupe; transaction ở nguồn không tự bảo đảm thứ tự xử lý tại mọi consumer.

### 17.4. External payment nằm ngoài SI

Một transaction trên Order không rollback được charge ở gateway. Cần paymentId, idempotent API, workflow state, compensation và reconciliation riêng.

## 18. SI trong NoSQL: đọc contract theo từng sản phẩm

Không nên khẳng định mọi sản phẩm sau đều **cung cấp SI cùng phạm vi**. Bảng này nêu những tính năng cần tra và điểm dễ nhầm:

| Hệ/họ | Cơ chế liên quan | Câu hỏi trước khi áp dụng |
|---|---|---|
| **MongoDB** | Multi-document transactions; snapshot read concern trên deployment hỗ trợ | Snapshot phạm vi nào, write concern nào, write conflicts và retry ra sao? |
| **DynamoDB** | Conditional writes và transaction APIs | Transaction isolation của API nào, region scope, item/action limits và retries? |
| **Cloud Firestore** | Transactions có semantics riêng và callback retry | Isolation thực tế, read-before-write, contention mode, SDK retry? |
| **Cosmos DB for NoSQL** | ETag, transactional batch/stored procedures trong logical partition | Các item có cùng partition key không, isolation và region mode ra sao? |
| **Couchbase** | Distributed transactions và transaction staging qua SDK | Isolation được tài liệu hóa, durability, cleanup và attempt retries? |
| **Cassandra/ScyllaDB** | LWT/conditional writes, batch với semantics riêng | Cơ chế nào bảo vệ một key/partition, có transaction nhiều record đúng phạm vi không? |
| **Redis** | Atomic command/Lua, WATCH/MULTI/EXEC | WATCH có ngăn writer từ snapshot cũ không, key-slot và persistence ra sao? |
| **Transactional KV** | MVCC/conflict range/serializable hoặc transaction model riêng | Mức isolation thực sự, conflict ranges, size/time limits và retry? |

### 18.1. MongoDB: snapshot read không tự là serializable

Trên deployment và API được hỗ trợ, MongoDB có multi-document transaction và `readConcern: "snapshot"` trong những điều kiện phù hợp. Điều này hữu ích để đọc trạng thái nhiều document theo một snapshot nhất quán. Nhưng không được coi chỉ riêng snapshot read là bằng chứng rằng **mọi predicate xuyên record** được bảo vệ serializable.

Các điểm cần xem:

- Session transaction thực sự bao phủ tất cả reads/writes chưa?
- Các reads có dùng cùng session không?
- Write conflict trên document được xử lý thế nào?
- Read concern, write concern và sharded topology có điều kiện nào?
- Snapshot có thể cũ và phải retry theo driver semantics như thế nào?

Ví dụ guard record ở mục trước là một cách **chủ động tạo write conflict** cho invariant, thay vì hy vọng snapshot tự ngăn write skew.

### 18.2. DynamoDB: transaction API không phải một nhãn SI chung

DynamoDB có atomic conditional writes và transaction APIs như `TransactWriteItems`/`TransactGetItems` theo phạm vi được hỗ trợ. Chúng có isolation/consistency contract riêng; không nên mô tả tất cả là “snapshot isolation” chỉ vì ứng dụng đọc nhiều item.

Đối với invariant nhiều item, cần đọc tài liệu về transaction scope, điều kiện, conflict, concurrent readers và global tables. Đối với invariant một item, một conditional update có thể đơn giản và phù hợp hơn transaction lớn.

### 18.3. Firestore: phải đọc isolation theo edition/mode

Firestore có transaction semantics và lựa chọn concurrency control phụ thuộc môi trường/edition. Không mặc định Firestore transaction chỉ là SI yếu cho phép write skew; hãy tra mức isolation được sản phẩm cam kết và cách SDK thực thi, gồm callback retry và điều kiện read-before-write.

Nếu sản phẩm hứa serializable cho transaction đúng phạm vi, test bác sĩ phải đối chiếu với **serializable**, không áp kỳ vọng “SI chắc chắn cho phép cả hai commit” một cách máy móc.

### 18.4. Cosmos DB for NoSQL: logical partition là ranh giới

Transactional batch/stored procedure thường có ràng buộc **một logical partition key** theo API. Nếu Order và Inventory ở hai logical partitions, không được suy rằng chúng có chung snapshot/atomicity từ một batch cục bộ.

Đọc thêm về `ETag`/`If-Match`, consistency, multi-region writes và các giới hạn của API đang dùng.

### 18.5. Couchbase: xem isolation/durability cụ thể

Couchbase có cơ chế transactions qua SDK và metadata staging/cleanup. Không suy từ việc SDK có callback rằng isolation chính xác là SI; cần xác minh phiên bản, topology và mức isolation được tài liệu hóa. Kiểm thử callback retry, conflict và cleanup sau crash.

### 18.6. Cassandra/ScyllaDB: LWT khác SI

CQL `IF`/LWT có thể bảo vệ conditional mutation trong phạm vi hỗ trợ, nhưng logged batch hoặc read consistency không tự thành SI/serializable transaction xuyên arbitrary partitions. Không xây invariant “ít nhất một doctor trực” trên hai partition rồi chỉ dựa vào hai LWT riêng.

### 18.7. Redis: atomic command không tự có MVCC snapshot

Redis `WATCH` kết hợp `MULTI/EXEC` có thể thực hiện optimistic concurrency trên key được theo dõi. Atomic script giúp check–modify một phạm vi được hỗ trợ. Nhưng không gọi đó là SI nhiều document nếu API không có hợp đồng snapshot tương ứng.

### 18.8. Transactional key–value không nhất thiết yếu hơn SI

Một số KV store có transaction nhiều key và cơ chế conflict detection mạnh hơn SI trong phạm vi nhất định. Luôn lấy isolation level từ **contract chính thức**, không suy mức bảo đảm từ kiểu dữ liệu key–value/document.

## 19. Snapshot trên nhiều shard và region

Trong hệ phân tán, một snapshot nhất quán **xuyên shard** không thể được suy đơn giản từ việc từng shard có MVCC.

### 19.1. Hai snapshot cục bộ chưa chắc là một snapshot toàn cục

~~~text
Shard A snapshot at logical point SA
Shard B snapshot at logical point SB
~~~

Nếu SA/SB không được phối hợp theo protocol của database, reader ghép giá trị từ hai thời điểm khác nhau có thể thấy read skew hoặc trạng thái không tồn tại đồng thời.

Một **distributed snapshot isolation** đúng nghĩa cần quy tắc chọn version/commit và visibility nhất quán trong phạm vi đã công bố. Một hệ chỉ hỗ trợ snapshot theo partition không hứa điều đó cho toàn cluster.

### 19.2. Read snapshot qua replica

Nếu T1 đọc shard A ở primary và B ở follower chậm, hai giá trị có thể không thuộc cùng mốc. Tùy DB, session/readConcern/consistency mode có thể phối hợp hoặc không. Không tạo một “snapshot” tự chế bằng hai GET rồi gắn cùng timestamp client.

### 19.3. Multi-region writer và conflict resolution

Hai region cùng ghi có thể được hòa giải last-write-wins hoặc theo chính sách khác. Một local transaction bảo vệ state tại region A không tự chứng minh invariant toàn cầu nếu region B cùng cho phép ghi.

Với số dư, tồn kho hoặc quota chặt, xem single-writer authority, escrow/quota theo region hoặc giao thức coordination mạnh theo nhu cầu.

### 19.4. Regional availability và real-time order

Ngay cả khi mỗi region trả read nhất quán theo state cục bộ, thứ tự thực tế giữa request ở hai region có thể không được bảo đảm nếu replication bất đồng bộ. Không đồng nhất SI với strict serializability toàn thế giới.

## 20. Thời gian sống của snapshot và chi phí vận hành

Một transaction đọc snapshot lâu có thể buộc engine giữ các phiên bản cũ:

~~~text
T0: Transaction T1 opens snapshot S100
T1: reads a large report for a long time
T2..T100: many writers commit new versions

Engine may need old versions for T1 until it ends.
~~~

Tùy engine, hậu quả có thể gồm:

- Tăng không gian giữ historical versions.
- Tăng áp lực GC/compaction hoặc lưu version chains.
- Tăng thời gian query trên snapshot cũ.
- Làm tăng contention/transaction abort khi cố cập nhật.
- Chạm transaction timeout hoặc snapshot lifetime limit.

### 20.1. Đừng giữ transaction mở trong lúc gọi HTTP

Không nên:

~~~text
BEGIN snapshot transaction
READ Cart
CALL external tax service (slow)
WAIT user confirmation
UPDATE Cart
COMMIT
~~~

External network/human interaction có thể kéo dài ngoài transaction deadline và làm snapshot cũ. Nên chuẩn bị trước những phần có thể chuẩn bị, rồi dùng transaction **ngắn** để kiểm tra lại những precondition bắt buộc và commit.

### 20.2. Transaction đọc lâu chưa chắc phù hợp OLTP

Một báo cáo đọc hàng triệu bản ghi trên snapshot lâu có thể ảnh hưởng write path. Cân nhắc read replica/reporting pipeline/snapshot export theo contract, nhưng đừng dùng projection trễ để quyết định invariant giao dịch.

### 20.3. Snapshot không miễn phí

Chi phí có thể xuất hiện dưới dạng version storage, metadata, commit tracking và retry. Chọn isolation và độ dài transaction dựa trên SLO, không chỉ lý luận rằng “đọc snapshot không khóa nên miễn phí”.

## 21. Test write skew trong một cơ sở dữ liệu thật

Một test concurrent nên cố tình tạo lịch:

~~~text
INITIAL:
    Doctor A = true
    Doctor B = true

T1:
    BEGIN snapshot transaction
    READ A, B
    BARRIER
    UPDATE A = false
    COMMIT

T2:
    BEGIN snapshot transaction
    READ A, B
    BARRIER
    UPDATE B = false
    COMMIT
~~~

### 21.1. Phép đo không chỉ là “cả hai client trả 200”

Ghi:

~~~text
transactionId / commandId
attemptId
start and finish timestamps
snapshot/version information if exposed
read values
write keys
commit/abort outcome
error class
final authoritative state
deployment topology / consistency config
~~~

Nếu cả hai commit và final count=0 dưới một hệ thực sự chỉ hứa SI, đây là **minh họa write skew**. Nếu sản phẩm hứa serializable cho phạm vi này, đó có thể là phản ví dụ cần điều tra sâu. Nếu hai bản ghi nằm ngoài transaction scope, test chưa kiểm chứng isolation mong muốn mà chỉ cho thấy thiết kế vượt bảo đảm.

### 21.2. Barrier để ép hai reads cùng snapshot

Hai worker bắt đầu cùng lúc chưa chắc đã đọc cùng trạng thái; scheduler và network có thể cho một transaction hoàn tất trước khi transaction kia đọc. Đặt barrier **sau khi cả hai đã đọc** và trước khi ghi giúp tăng cơ hội tái hiện write skew.

### 21.3. Cẩn thận với auto-retry callback

Một số SDK có thể tự chạy lại transaction callback khi conflict. Nếu barrier luôn đợi đủ hai worker ở mọi attempt, lần retry có thể bị kẹt vì worker kia đã hoàn tất. Chỉ dùng barrier cho attempt đầu hoặc thiết kế test hook có kiểm soát.

### 21.4. Không dùng test để gán isolation sai cho sản phẩm

Nếu DB đã cam kết serializable, expected test là một transaction có thể abort/retry và invariant không bị phá. Nếu DB cam kết SI, test write skew giúp minh họa rủi ro. Cần ghi rõ mức isolation đang yêu cầu và đã bật thật chưa.

## 22. Java: một abstraction cho test hai bác sĩ

Để tránh giả định API transaction của một vendor, có thể tạo một adapter phục vụ integration test:

~~~java
public record WardId(String value) {}
public record DoctorId(String value) {}

public enum EndShiftResult {
    ENDED,
    LAST_DOCTOR_MUST_STAY,
    KNOWN_CONFLICT_ABORT,
    UNKNOWN_COMMIT
}

public interface WardTransactionAdapter {
    void resetWard(
        WardId ward, DoctorId doctorA, DoctorId doctorB
    );

    // Must use a real transaction on the target NoSQL database.
    // Test adapter may expose a callback after dependent reads.
    EndShiftResult endShift(
        WardId ward,
        DoctorId doctor,
        String commandId,
        Runnable afterReadsBarrier
    );

    int authoritativeOnCallCount(WardId ward);
}
~~~

### 22.1. JUnit test skeleton

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class SnapshotIsolationWriteSkewTest {
    private final WardTransactionAdapter adapter =
        TestEnvironment.wardAdapter();

    @Test
    void concurrentShiftEndingsExposeIsolationContract()
            throws Exception {
        WardId ward = new WardId("ward-test-1");
        DoctorId a = new DoctorId("A");
        DoctorId b = new DoctorId("B");
        adapter.resetWard(ward, a, b);

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch proceed = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        Runnable firstAttemptBarrier = () -> {
            ready.countDown();
            try {
                if (!proceed.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("barrier timeout");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new RuntimeException(ex);
            }
        };

        try {
            Future<EndShiftResult> f1 = pool.submit(() ->
                adapter.endShift(ward, a, "command-A",
                    firstAttemptBarrier));
            Future<EndShiftResult> f2 = pool.submit(() ->
                adapter.endShift(ward, b, "command-B",
                    firstAttemptBarrier));

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            proceed.countDown();

            EndShiftResult r1 = f1.get(20, TimeUnit.SECONDS);
            EndShiftResult r2 = f2.get(20, TimeUnit.SECONDS);

            int onCall = adapter.authoritativeOnCallCount(ward);

            // For SI without a shared guard, this assertion
            // may FAIL: that failure demonstrates write skew.
            // For a correct guard/serializable design it must hold.
            assertTrue(onCall >= 1,
                "Business invariant violated; outcomes: "
                    + r1 + ", " + r2);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Đây là **test skeleton**; `TestEnvironment` phải do nhóm tự triển khai để kết nối database và cấu hình thực tế. Test này có thể **được kỳ vọng thất bại** khi cố tình chạy mô hình naive dưới SI nhằm minh họa write skew. Khi bật guard/serializable, bất biến phải được giữ.

### 22.2. Hạn chế của skeleton

- Barrier không bảo đảm hai transaction thật sự cùng snapshot nếu adapter không đặt tại điểm sau read.
- `Runnable` được giả định chỉ gọi một lần trong initial attempt; adapter dùng auto retry phải quản lý barrier theo attempt.
- Kết quả `UNKNOWN_COMMIT` cần đối soát bằng commandId trước khi kết luận.
- Không được chạy trên dữ liệu production; resetWard chỉ dùng namespace test cô lập.
- Cần lặp nhiều seed/lịch chạy và thu transaction history để có bằng chứng tốt hơn.

### 22.3. Viết thêm test positive cho guard

Sau khi thay endpoint để mọi transaction ghi WardGuard, chạy cùng harness. Mong đợi **không cả hai cùng kết thúc ca**. Một transaction có thể abort vì conflict hoặc trả `LAST_DOCTOR_MUST_STAY` sau retry. Đừng đòi cả hai success nếu invariant cấm.

## 23. Test predicate anomaly với username

Test:

~~~text
Tạo namespace tenant mới, chưa có username "an123".

T1:
    query username=an123 -> absent
    wait barrier
    insert User(U1, an123)

T2:
    query username=an123 -> absent
    wait barrier
    insert User(U2, an123)

commit both if database allows.
~~~

Đo:

- Số transaction commit.
- Số user có cùng canonicalUsername trong nguồn.
- Có unique key/constraint thật không.
- Query có thuộc transaction snapshot đúng scope không.
- Lỗi nào báo conflict/duplicate.

Nếu một `UsernameRegistry` conditional insert trên key chung được dùng, kỳ vọng tối đa một winner. Nếu chỉ query không có guard, cả hai insert khác ID có thể thành công theo SI chuẩn.

### 23.1. Không nhầm read query với uniqueness constraint

Một query `COUNT = 0` tại snapshot không khóa logic “mọi record tương lai có username này” trừ khi engine/isolation có cơ chế bảo vệ predicate hoặc unique key.

### 23.2. Test across partitions

Nếu username registry được partition theo tenant, phải đảm bảo uniqueness yêu cầu cũng chỉ trong tenant. Nếu business yêu cầu uniqueness **toàn cầu**, key partition và giao thức phân tán phải phản ánh phạm vi đó.

## 24. Test quota và counter

Cho quota 10, active reservations hiện có 5. Hai transaction cùng muốn reserve 4:

~~~text
T1 read SUM=5 -> insert R2 qty=4
T2 read SUM=5 -> insert R3 qty=4
~~~

**Mô hình naive:** nếu insert hai record riêng và không có conflict, final SUM=13.

**Mô hình quota owner:**

~~~text
Quota.available = 5

T1 conditional decrement 4 -> available=1
T2 conditional decrement 4 -> fails, available<4
~~~

Nhưng nếu hệ dùng quota owner và reservation record khác partition, phải bảo vệ hai thay đổi trong transaction hoặc có idempotent workflow/ledger để không giữ quota mất đồng bộ.

### 24.1. Đo cả external retry

Nếu request trừ quota thành công nhưng client timeout rồi gửi lại, cần commandId để tránh trừ hai lần. SI hay atomic decrement không tự cung cấp exactly-once processing của request.

## 25. Khi một long-running transaction dùng snapshot cũ

Giả sử một tác vụ duyệt giá:

~~~text
t0: T1 BEGIN snapshot, Price=100
t1: T2 updates Price=120; COMMIT
t2: T1 checks Price<=100 using snapshot
t3: T1 writes Approval record
t4: T1 COMMIT
~~~

Nếu T1 không ghi Price hoặc một guard liên quan, một SI transaction có thể commit Approval dựa trên giá cũ. Đây có thể là hành vi hợp lệ dưới contract isolation, nhưng sai nếu business rule yêu cầu “không duyệt giá vượt 100 tại thời điểm commit”.

### 25.1. Giải pháp là commit-time precondition

Nếu Approval phải phụ thuộc Price hiện tại:

- Dùng serializable transaction đúng scope.
- Cập nhật guard/version của Price trong cùng transaction để tạo conflict.
- Thiết kế Approval là state transition trên cùng aggregate chứa price/version.
- Dùng conditional update/compare-and-set phù hợp.

### 25.2. Business có thể cho phép snapshot cũ

Không phải mọi snapshot cũ đều sai. Ví dụ báo cáo doanh thu “tính đến 12:00” có thể cần snapshot nhất quán ở mốc đó. Điều quan trọng là **hợp đồng nghiệp vụ nêu rõ cần dữ liệu của mốc nào**, không mặc định luôn cần newest.

## 26. Các trường hợp cần phân biệt SI với lỗi do thiết kế transaction

### 26.1. Write skew thật

Hai transaction cùng nhìn snapshot hợp lệ, ghi các item khác nhau, cùng commit làm sai invariant xuyên item. Đây là vấn đề đặc trưng có thể xuất hiện dưới SI.

### 26.2. Read skew do ghép nhiều API không cùng snapshot

Ứng dụng đọc Account A ở thời điểm t1 và Account B từ replica trễ ở t2. Không phải transaction SI trên A/B nếu hai read không nằm trong snapshot scope chung.

### 26.3. Lost update do replace ngoài transaction

Client dùng full document cũ mà không gửi version condition. Không kết luận SI đã không ngăn lost update nếu transaction SI không bao gồm thao tác đọc đó.

### 26.4. Partial commit do tách hai transaction

Order và Outbox được ghi hai request khác nhau trong một hệ chỉ có transaction một partition. Lỗi là thiếu **atomic boundary**, không phải SI của từng request.

### 26.5. Stale reader từ secondary index

Search chưa thấy Order mới dù Order transaction đã commit. Đây thường là vấn đề **visibility/replication/eventual index**, cần đo riêng.

### 26.6. Duplicate do retry request

Client timeout rồi gửi cùng command với ID khác. Database có thể commit hai transaction hoàn toàn hợp lệ. Lỗi là thiếu **idempotency ở tầng nghiệp vụ**, không phải nhất thiết isolation anomaly.

## 27. Monitoring: đo isolation và vi phạm invariant

Các metric có ích:

| Metric | Ý nghĩa |
|---|---|
| Transaction conflict/abort rate | Mức tranh chấp và chi phí isolation |
| Serialization failures | Tần suất engine từ chối history không hợp lệ |
| Snapshot age / active transaction age | Transaction đọc snapshot cũ trong bao lâu |
| MVCC version retention/backlog | Phiên bản cũ có làm tăng storage pressure không |
| Hot key/guard contention | Guard có trở thành nút nghẽn không |
| Transaction p95/p99 | Độ trễ và retry impact |
| Write skew/invariant check failures | Có dấu hiệu vi phạm quy tắc chung không |
| Conditional update failed by predicate | Từ chối do quota/status/version |
| Unknown commit outcomes | Bao nhiêu request cần reconciliation |
| Idempotency duplicate prevented | Có chặn request lặp không |
| Replica/index lag | Dữ liệu dẫn xuất chậm bao lâu |
| Distributed transaction/partition failures | Mất tính sẵn sàng theo topology |

### 27.1. Invariant audit

Với quota, có thể chạy job đối soát:

~~~text
Assert:
    SUM(activeReservations.quantity) <= roomCapacity
    Quota.available + SUM(activeReservations.quantity) == totalCapacity
~~~

Với ca trực:

~~~text
Assert:
    COUNT(onCallDoctors per ward) >= 1
~~~

Những job này không thay thế ngăn lỗi tại commit, nhưng giúp phát hiện regression, writer bỏ qua guard, lỗi migration hoặc dữ liệu bị sai từ trước.

### 27.2. Tách conflict khỏi business rejection

`LAST_DOCTOR_MUST_STAY` là từ chối nghiệp vụ hợp lệ. `WRITE_CONFLICT` là xung đột có thể retry. `TRANSACTION_TOO_LARGE` là giới hạn thiết kế. `UNKNOWN_COMMIT` cần đối soát. Gộp hết thành “transaction failed” khiến vận hành khó tìm nguyên nhân.

### 27.3. Bảo mật dữ liệu test/trace

Trace transaction nên ghi key/IDs được bảo vệ, read/write set và outcome; không đưa dữ liệu nhạy cảm cá nhân, token hoặc thông tin thanh toán vào log kỹ thuật chỉ để nghiên cứu SI.

## 28. Tradeoff khi chọn phương án bảo vệ

| Phương án | Ưu điểm | Hạn chế/cần xác minh |
|---|---|---|
| **Single aggregate/document** | Một atomic conditional update, dễ bảo vệ invariant | Giới hạn kích thước, hot document, bounded growth |
| **Guard record** | Biến write skew thành write conflict | Mọi writer phải tuân thủ; guard hotspot; cần transaction với record phụ |
| **Serializable transaction** | Bảo vệ nhiều anomaly trong đúng scope | Conflict/retry, chi phí và giới hạn topology |
| **Unique/conditional key** | Hiệu quả cho uniqueness hoặc ownership | Cần thiết kế key và lifecycle nhất quán |
| **Atomic quota decrement** | Kiểm tra và giảm trên một nguồn | Phải xử lý reservationId, retry/timeout và item phụ |
| **Single writer/queue** | Tuần tự hóa quyết định cho một owner | Backlog, failover, idempotency, latency |
| **Quota/escrow theo shard/region** | Giảm tranh chấp global key | Phải cấp quota trước và quản lý rebalancing |
| **Saga/compensation** | Phù hợp nhiều service | Không ẩn trạng thái trung gian; phải bù và đối soát |

### 28.1. Không chọn theo nhãn “mạnh nhất” một cách cơ học

Nếu invariant chỉ thuộc một Inventory item, atomic conditional decrement có thể đơn giản hơn transaction serializable nhiều item. Nếu invariant thật sự xuyên nhiều record và SI không đủ, phải có cơ chế mạnh hơn hoặc thay đổi thiết kế.

### 28.2. Đo cost trong chính workload

Một guard record được sửa mỗi khi hàng nghìn request cùng xử lý có thể làm throughput thấp. Nhưng bỏ guard để tăng throughput rồi cho phép oversell không phải tối ưu. Cần thử queue/quota, thiết kế partition mới hoặc tách invariant đúng nghĩa.

### 28.3. Cần đảm bảo source of truth

Nếu một index/cached count không phải nguồn có thẩm quyền, transaction bảo vệ nó vẫn có thể bỏ sót writer cập nhật nguồn thật. Xác định rõ owner và trách nhiệm cập nhật trên mọi đường ghi.

## 29. Những ngộ nhận phổ biến

### “Dùng snapshot thì tất cả đọc/ghi trong transaction đều serializable”

Không. SI có thể cho phép write skew và predicate anomalies.

### “Hai transaction không ghi cùng record nên chắc chắn không liên quan”

Sai. Chúng có thể cùng dựa trên một bất biến xuyên nhiều record.

### “Write skew là lỗi atomicity”

Không. Hai transaction có thể atomically commit riêng nhưng history không serializable.

### “SI luôn có phantom khi query lại”

Trong **snapshot cố định đúng nghĩa**, query lặp lại không nhìn thấy bản ghi mới sau snapshot. Bất thường còn lại là những **transaction tạo record khác nhau cùng vi phạm predicate sau commit**, không phải nhất thiết phantom trong read lặp.

### “SI luôn cho phép lost update trên cùng record”

Không đúng với SI chuẩn có write conflict detection. Nhưng application có thể tạo lost update nếu đọc/ghi ngoài ranh giới bảo vệ.

### “MVCC đồng nghĩa SI”

Không. MVCC là kỹ thuật quản lý phiên bản, có thể phục vụ nhiều isolation level khác nhau.

### “Serializable tự động linearizable theo thời gian thật”

Không. Strict serializability thêm yêu cầu thứ tự real-time.

### “Strong read từ một replica đủ bảo vệ transaction nhiều document”

Không tự động. Isolation của transaction và freshness của một read là hai câu hỏi.

### “Một transaction snapshot trên Order bảo vệ Inventory ở service khác”

Không. Bất biến vượt transaction scope cần cơ chế khác.

### “Chỉ cần query COUNT lần nữa trước commit”

Nếu query vẫn thuộc cùng snapshot cũ, kết quả có thể không đổi. Cần predicate/guard/serializable phù hợp.

### “Có guard thì có thể bỏ mọi transaction”

Nếu guard và dữ liệu phụ được cập nhật ở hai item độc lập, vẫn có nguy cơ partial commit. Phải xác minh atomic boundary.

### “Có serializable thì không cần xử lý conflict”

Một transaction có thể bị abort để giữ serializability. Ứng dụng cần retry đúng.

### “Có SI nghĩa là snapshot toàn cluster và mọi region”

Không mặc nhiên. Phạm vi snapshot phụ thuộc API/topology.

### “Read replica trễ chứng minh transaction source hỏng”

Chưa chắc. Có thể là replication lag/consistency mode được cho phép.

### “Ứng dụng đã kiểm tra invariant ở Java nên database không cần kiểm tra”

Đọc–kiểm tra–ghi tách rời có race; cần điều kiện ở commit hoặc transaction đủ mạnh.

### “Timeout sau commit tức transaction abort”

Không. Cần idempotency và đối soát unknown outcome.

### “Transaction mạnh hơn sẽ tự sửa sai số liệu đã có”

Không. Invariant có thể đã bị phá trước đó do writer cũ, dữ liệu migration hoặc logic sai. Cần audit/repair và ngăn tái diễn.

## 30. Quy trình thiết kế một tính năng dưới snapshot isolation

1. **Viết invariant** bằng một biểu thức kiểm chứng được.
2. **Xác định owner** và các item/predicate mà invariant phụ thuộc.
3. **Xác định transaction scope:** một item, logical partition, nhiều shard hay service.
4. **Đọc contract isolation thật:** SI, serializable hoặc tính năng snapshot read có giới hạn.
5. **Vẽ lịch cạnh tranh:** ít nhất hai transaction cùng đọc invariant.
6. **So sánh write sets:** nếu hai transaction có thể ghi item khác nhau, xem xét write skew.
7. **Kiểm tra predicate inserts/deletes:** một truy vấn COUNT/absence có được bảo vệ lúc commit không?
8. **Chọn phương án bảo vệ:** same-document atomic update, guard record, unique key, serializable hay quota owner.
9. **Kiểm tra mọi writer:** background job, admin tool, consumer, migration đều tuân thủ.
10. **Thiết kế retry:** transaction abort được chạy lại từ đầu; business rejection không retry mù.
11. **Thiết kế idempotency:** commandId ổn định qua timeout và request gửi lặp.
12. **Tách external effects:** outbox và saga khi vượt atomic boundary.
13. **Chạy concurrency test:** barrier sau reads, nhiều lịch, authoritative final-state check.
14. **Chạy fault test:** commit ACK mất, failover, replica lag, cross-region nếu liên quan.
15. **Đo vận hành:** conflict rate, snapshot age, hot keys, p99 và invariant audit.

### 30.1. Mẫu quyết định kỹ thuật

~~~yaml
useCase: stop-doctor-shift
businessInvariant: "at least one doctor on-call per ward"
sourceOfTruth: "Ward aggregate / Guard record"
records:
  - "Doctor A"
  - "Doctor B"
  - "WardGuard for one shift"
transactionScope: "<verified product and topology scope>"
isolation: "<documented level>"
risk:
  - "write skew when two doctors quit concurrently"
solution:
  - "every transaction conditionally updates the same WardGuard"
  - "doctor state and guard commit in the same supported transaction"
retry:
  - "confirmed write conflict: redo entire UoW"
  - "last doctor condition: reject as business rule"
  - "unknown commit: reconcile by stable commandId"
observability:
  - "transaction conflict rate"
  - "guard hot key latency"
  - "periodic on-call invariant audit"
tests:
  - "two concurrent leave commands"
  - "write conflict and retry"
  - "commit ACK lost"
  - "background writer update"
~~~

Phần placeholder phải được điền theo sản phẩm thật; đây không phải một hợp đồng transaction đã được xác minh.

## 31. Bài tập thực hành

### Bài 1 — Lịch write skew bác sĩ

Hai bác sĩ A, B cùng trực. T1 đọc cả hai và cho A nghỉ; T2 đọc cả hai và cho B nghỉ. Viết lịch R/W/COMMIT cho cả hai. Chứng minh không tồn tại thứ tự serial tương ứng khi cả hai commit.

### Bài 2 — Dirty read và repeatable read

T1 bắt đầu ở snapshot S100, đọc `Price=100`; T2 cập nhật `Price=120` rồi commit. T1 đọc lại Price. Hãy giải thích kết quả của SI chuẩn, và vì sao điều đó không có nghĩa T1 đang đọc giá mới nhất.

### Bài 3 — Phantom hay predicate anomaly?

Hai transaction đều query không có username `an123`, sau đó insert hai User với ID khác nhau. Giải thích tại sao hai query cùng trả 0 và lặp query trong snapshot vẫn ổn định nhưng uniqueness có thể bị phá.

### Bài 4 — Quota 10 chỗ

Room có 10 chỗ, hiện giữ 5. Hai transaction cùng insert reservation 4 chỗ dựa trên SUM=5. Phân tích write skew và thiết kế atomic counter/guard hoặc serializable transaction thích hợp.

### Bài 5 — Serialization graph

Với T1 đọc B rồi ghi A và T2 đọc A rồi ghi B, hãy vẽ hai cạnh read–write anti-dependency và giải thích chu trình gây non-serializable history.

### Bài 6 — Single-document Ward

Thiết kế một Ward document giữ danh sách bác sĩ trực bounded. Viết điều kiện nguyên tử để xóa A chỉ khi còn ít nhất hai bác sĩ đang trực. Nêu giới hạn kích thước/hot document.

### Bài 7 — Guard record

Thiết kế `WardGuard(onCallCount, version)` và transaction cập nhật Guard cùng Doctor. Nếu transaction T1 giảm count từ 2 xuống 1, T2 phải xử lý ra sao khi retry? Vì sao mọi writer phải tuân thủ Guard?

### Bài 8 — MongoDB transaction

Chuyển bài toán Doctor A/B thành hai update khác nhau trong một transaction snapshot. Phân tích rủi ro nếu không cập nhật Guard. Thêm Guard và chỉ ra record gây write conflict.

### Bài 9 — So sánh isolation

Lập bảng cho read committed, SI, serializable và strict serializable: snapshot visibility, write skew, thứ tự real-time. Nêu vì sao tên `repeatable read` không đủ để suy ra SI cho mọi engine.

### Bài 10 — Multi-region inventory

Hai region nhận giữ 8 sản phẩm khi tổng tồn là 10 và replication trễ. SI cục bộ có đủ không? Đề xuất single-writer hoặc preallocated quotas và cách kiểm tra kết quả sau convergence.

### Bài 11 — Test harness

Viết một JUnit concurrency test dùng barrier sau read cho hai bác sĩ. Thiết kế positive test cho guard và negative test cho naive SI. Cần thu những thông tin gì từ transaction history?

### Bài 12 — Callback auto-retry

SDK có thể tự chạy lại callback sau write conflict. Vì sao barrier đặt trong mỗi attempt có thể deadlock? Vì sao gửi email từ callback có nguy cơ phát trùng?

### Bài 13 — Snapshot lâu

Một transaction giữ snapshot trong 10 phút trong khi có nhiều writer mới. Phân tích ảnh hưởng tới stale business decisions, version retention và thời gian khôi phục tài nguyên. Khi nào snapshot cũ lại là đúng nhu cầu?

### Bài 14 — Unknown commit và idempotency

Một transaction giảm `Quota.available` thành công nhưng response timeout. Client retry với commandId mới. Hãy giải thích vì sao đây là lỗi dù update trên một item nguyên tử, và thiết kế reservationId để dedupe.

### Bài 15 — Review một tuyên bố kiến trúc

Một tài liệu nội bộ viết “Database dùng MVCC và strong reads, nên transaction của mọi Order và Inventory là serializable trên các vùng; không cần CAS”. Hãy liệt kê các suy luận sai và các bằng chứng/documentation/test phải có trước khi chấp nhận tuyên bố.

### Bài 16 — Sai lệch đã tồn tại

WardGuard ghi count=2 nhưng chỉ còn một Doctor thực sự trực vì một job cũ bỏ qua Guard. Transaction mới dùng condition count>1 và cho người cuối cùng nghỉ. Hãy đề xuất cách ngăn writer bỏ qua protocol, audit/repair dữ liệu và quyết định nguồn có thẩm quyền.

---

**Kết luận:** Snapshot isolation cung cấp **một ảnh chụp đọc ổn định và loại bỏ nhiều bất thường đọc**, nhưng nó không tự tạo một thứ tự tuần tự hợp lệ cho mọi transaction. Bất thường cốt lõi là **write skew**: hai transaction đọc cùng invariant, ghi những record khác nhau và cùng commit làm invariant sai, dù từng transaction riêng vẫn atomic. Predicate checks như “không có username này” hoặc “tổng reservation chưa vượt quota” cũng có thể bị phá khi không được bảo vệ ở commit. Trong NoSQL, giải pháp phải đi từ **nguồn có thẩm quyền và phạm vi transaction thật**, chọn **atomic document/conditional key, guard record hoặc serializable isolation** phù hợp, rồi kiểm thử race, retry, read consistency và failover theo đúng contract của sản phẩm. **Snapshot nhất quán không đồng nghĩa serializable, snapshot mới nhất, transaction xuyên service hay bảo đảm toàn cầu ở mọi region.**
