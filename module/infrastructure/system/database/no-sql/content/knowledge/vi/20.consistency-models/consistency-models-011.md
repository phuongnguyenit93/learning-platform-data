# Phạm vi bảo đảm theo khóa, phân vùng, giao dịch, phiên hoặc vùng triển khai

## 1. Vì sao phải nói rõ *phạm vi* của bảo đảm nhất quán?

Trong hệ thống NoSQL, câu “database này nhất quán mạnh” hoặc “database kia chỉ nhất quán cuối cùng” thường **chưa đủ để thiết kế một tính năng đúng**. Cần hỏi thêm:

> Bảo đảm đó áp dụng cho **một khóa**, **một phân vùng**, **một giao dịch nhiều bản ghi**, **một phiên client**, hay **mọi bản sao thuộc nhiều vùng địa lý**?

Giả sử một nền tảng bán hàng lưu:

~~~text
Inventory[P100]       -> available = 1
Order[O100]           -> status = CREATED
OrdersByCustomer[U1]  -> danh sách đơn của U1
SearchIndex[P100]     -> tài liệu tìm kiếm sản phẩm
~~~

Ứng dụng có thể có các bảo đảm khác nhau trong cùng một thời điểm:

- Cập nhật có điều kiện trên `Inventory[P100]` được áp dụng nguyên tử.
- `Inventory[P100]` và `Order[O100]` **không** tự động cùng commit.
- Sau khi tạo đơn, chính client đặt hàng có thể đọc thấy đơn trong một phiên.
- Một client khác ở region xa có thể thấy đơn chậm hơn vì sao chép bất đồng bộ.
- `OrdersByCustomer` có thể là read model cập nhật sau nguồn.
- `SearchIndex` có thể cần thời gian refresh trước khi tài liệu mới xuất hiện trong tìm kiếm.

Mỗi câu đều liên quan **consistency**, nhưng ở các phạm vi hoàn toàn khác nhau. Không thể suy ra bảo đảm của toàn hệ chỉ từ một tham số “strong” trong SDK.

### 1.1. Tình huống xuyên suốt

Hai client đặt món hàng P100; tại thời điểm đầu chỉ có một sản phẩm:

~~~json
{
  "productId": "P100",
  "available": 1,
  "version": 12
}
~~~

Nếu database bảo đảm một **conditional decrement trên cùng khóa** là nguyên tử, tối đa một request có thể giảm `available` từ 1 xuống 0.

Nhưng sau khi giảm thành công, ứng dụng còn phải:

1. Tạo `Order[O100]`.
2. Cập nhật danh sách đơn theo khách hàng.
3. Phát sự kiện cho hệ vận chuyển.
4. Hiển thị trạng thái ở region khác.

Bảo đảm per-key cho tồn kho **không đủ** để trả lời liệu cả bốn bước sau đã hoàn tất. Chúng cần bảo đảm theo **giao dịch, phiên, vùng hoặc read model** tương ứng.

## 2. Hai trục khác nhau: mức nhất quán và phạm vi áp dụng

Để tránh nhầm lẫn, tách hai trục:

**Trục A — Bảo đảm về thứ tự/quan sát dữ liệu:** linearizability, sequential consistency, causal consistency, eventual consistency, bounded staleness, snapshot/serializable transaction, session guarantees...

**Trục B — Phạm vi:** khóa hoặc document, phân vùng, transaction, phiên client, region, nhóm region hoặc toàn bộ hệ.

Không nên xếp tất cả vào một danh sách “mạnh → yếu” duy nhất mà quên scope.

| Phạm vi | Câu hỏi cốt lõi | Ví dụ bảo đảm có thể có |
|---|---|---|
| Một khóa/document | Hai ghi cùng key có được sắp thứ tự và đọc thấy đúng không? | Atomic update, conditional write, linearizable operation |
| Một phân vùng | Nhiều row trong một partition được quan sát/ghi theo quy tắc nào? | Partition-local ordering, batch/transaction trong phạm vi được hỗ trợ |
| Một giao dịch | Nhiều thao tác có commit cùng nhau và cô lập trước concurrent writes không? | Atomicity, snapshot isolation, serializability |
| Một phiên client | Sau khi ghi/đọc, chính client đó có nhìn dữ liệu đi lùi không? | Read-your-writes, monotonic reads/writes, writes-follow-reads |
| Một region | Client qua các replica nội vùng nhìn thấy gì? | Strong read, quorum, read-after-write theo cấu hình |
| Nhiều region | Ghi tại vùng A khi nào đọc được ở B? Hai vùng có thể cùng xác nhận ghi xung đột không? | Regional replication contract, conflict resolution, globally coordinated consistency |
| Read model bên ngoài | Search/cache/index phụ có theo kịp nguồn không? | Async projection, bounded freshness SLO, reconciliation |

Một hệ có thể **mạnh trên khóa** nhưng **yếu giữa các region**. Một client có thể nhận **session consistency** dù một client khác ở cùng region chưa thấy bản ghi. Một transaction có thể bảo vệ nhiều document nhưng chỉ trong những giới hạn topology nhất định.

## 3. Khái niệm nền tảng: operation, replica, authority và lịch sử quan sát

### 3.1. Operation

Một operation có thể là:

- `GET(K)`;
- `PUT(K, v)`;
- `UPDATE(K) IF version = n`;
- `DELETE(K)`;
- Một transaction chứa nhiều reads/writes;
- Một query theo index;
- Một lệnh đọc qua cache/read model.

Khi đánh giá consistency, phải biết **operation nào thuộc hợp đồng**. Đọc qua nguồn chính và đọc qua search index thường không có cùng bảo đảm.

### 3.2. Replica

Một khóa có thể được lưu trên nhiều máy:

~~~text
                   K = balance:U42
                           |
              +------------+------------+
              |            |            |
              v            v            v
         Replica A    Replica B    Replica C
~~~

Một client có thể đọc replica gần nhất, leader, follower hoặc nhóm quorum tùy cấu hình.

### 3.3. Authority

**Authority** là nơi hoặc giao thức có quyền xác định trạng thái hợp lệ khi có xung đột. Nó có thể là:

- Leader của partition;
- Quorum có đủ điều kiện;
- Coordinator của transaction;
- Hệ đồng thuận;
- Một record có conditional write;
- Một event log duy nhất theo business key.

“Có nhiều replica” **không có nghĩa** mọi replica độc lập đều được quyết định một invariant toàn cục.

### 3.4. Thời điểm ghi được xác nhận

Xét:

~~~text
T0: Client A PUT(K, v2)
T1: Database trả "success"
T2: Client B GET(K)
~~~

Nếu `GET` của B được bảo đảm nhìn thấy v2 khi không có ghi mới hơn và B dùng đúng đường đọc theo hợp đồng, đó là một loại read-after-write mạnh. Nếu chỉ có eventual consistency, B có thể đọc v1 ở T2.

Nhưng còn phải hỏi:

- A ghi với write concern nào?
- B đọc từ nơi nào?
- B có sử dụng session token không?
- Có nhiều region không?
- Có một read model cập nhật chậm không?
- Có network partition hoặc failover không?

**Response success chỉ có ý nghĩa trong phạm vi và mức xác nhận được sản phẩm cam kết.**

## 4. Các mức nhất quán thường gặp và điều chúng *không* tự bảo đảm

### 4.1. Linearizability

Với những operation thuộc phạm vi được bảo đảm, kết quả có thể được giải thích như thể mỗi operation xảy ra tại một thời điểm duy nhất giữa lúc gọi và lúc trả lời, đồng thời **tôn trọng thứ tự thời gian thực**.

Nếu A hoàn tất ghi `K=v2` trước khi B bắt đầu đọc K, và không có ghi nào mới hơn, một read linearizable phù hợp không thể hợp lệ trả v1.

~~~text
A: PUT K=v2       [-------- success]
B: GET K                            [---- result v2]
                     thời gian --->
~~~

**Cảnh báo phạm vi:** linearizability của `K1` và `K2` riêng lẻ không tự tạo ra một transaction nguyên tử cập nhật cả hai khóa.

### 4.2. Sequential consistency

Các operation có thể được xếp trong một thứ tự tuần tự giữ đúng **thứ tự chương trình của từng client**, nhưng không nhất thiết giữ mọi quan hệ thời gian thực giữa client khác nhau.

Vì vậy sequential consistency nói về thứ tự quan sát, nhưng yếu hơn linearizability ở yêu cầu **real-time order**.

### 4.3. Causal consistency

Nếu sự kiện B **phụ thuộc nhân quả** vào A, các client quan sát cả hai phải tôn trọng thứ tự A rồi B theo bảo đảm của hệ.

Ví dụ:

~~~text
A: Đăng bài P
B: Đọc P rồi trả lời comment C
~~~

B phụ thuộc P. Một quan sát tuân thủ causal consistency không được trình bày C như thể xuất hiện trước P trong ngữ cảnh liên quan.

Hai ghi độc lập, không có phụ thuộc nhân quả, có thể được nhìn thấy theo các thứ tự khác nhau. **Causal consistency không phải một thứ tự toàn cục cho mọi operation.**

### 4.4. Eventual consistency

Nếu không có ghi mới, các replica hợp lệ cuối cùng sẽ hội tụ về trạng thái tương thích với cơ chế của hệ, theo điều kiện hoạt động mà dịch vụ cam kết.

Trong khoảng trước hội tụ, một client có thể:

- Đọc giá trị cũ;
- Đọc giá trị khác tùy replica;
- Không thấy bản ghi mới;
- Thấy một projection chưa cập nhật.

**“Eventual” không mang một giới hạn thời gian tuyệt đối** nếu sản phẩm không công bố và bảo đảm một giới hạn cụ thể. Không nên tự hứa “mọi replica sẽ đúng sau 100 ms” chỉ vì môi trường thử nghiệm thường nhanh.

### 4.5. Bounded staleness

Một số sản phẩm có mô hình cho phép độ trễ phiên bản hoặc thời gian tối đa trong điều kiện được định nghĩa.

Ví dụ mô hình:

~~~text
Replica có thể chậm tối đa K phiên bản
hoặc tối đa T đơn vị thời gian
~~~

Chi tiết về K, T và khi mạng lỗi phụ thuộc hợp đồng sản phẩm. Khi không thể thỏa bound, hệ có thể tăng latency hoặc làm một số thao tác không khả dụng; không được mặc định nó vẫn luôn trả giá trị cũ vô hạn mà vẫn giữ lời hứa.

### 4.6. Consistent prefix

Client có thể nhìn một **tiền tố hợp lệ** của chuỗi cập nhật, không quan sát thứ tự bị đảo trong luồng mà mô hình này áp dụng.

Nếu có các update:

~~~text
v1 -> v2 -> v3
~~~

một client có thể chưa thấy v3 nhưng không được thấy một trạng thái thể hiện v3 mà bỏ qua quan hệ thứ tự cần giữ theo hợp đồng prefix.

Không nên đánh đồng consistent prefix với serializable transaction xuyên toàn bộ dữ liệu.

### 4.7. Session consistency

Bảo đảm gắn với **một chuỗi operation được nhận diện là cùng phiên logic**. Nó có thể gồm read-your-writes, monotonic reads, monotonic writes và writes-follow-reads.

Session consistency **không có nghĩa** mọi client khác nhìn thấy dữ liệu mới ngay lập tức.

### 4.8. Isolation của transaction

Một hệ có thể hỗ trợ snapshot isolation hoặc serializable isolation cho một transaction trong khi các truy vấn đơn lẻ qua replica khác vẫn dùng chính sách consistency khác.

**Transaction isolation và replica consistency là hai trục liên quan nhưng không đồng nhất.**

## 5. Phạm vi theo khóa (per-key consistency)

### 5.1. Một khóa là gì?

Tùy NoSQL, khóa là:

- Một Redis key;
- Một DynamoDB item với partition key và sort key;
- Một MongoDB document theo `_id`;
- Một Firestore document path;
- Một HBase row key;
- Một document trong Couchbase;
- Một aggregate/cell theo quy tắc Cassandra.

Không nên tự suy “khóa” luôn tương đương **partition**. Nhiều item có thể nằm chung partition; một item không phải toàn bộ partition.

### 5.2. Atomic update trên một khóa

Ví dụ bộ đếm:

~~~text
Counter[page:A] = 100

Client A: INCREMENT 1
Client B: INCREMENT 1
~~~

Nếu database cung cấp atomic increment trên key, kết quả sau hai mutation đã áp dụng có thể là 102.

Điều này giải quyết lỗi **lost update** cho phép tăng đơn giản. Nó không tự đảm bảo một report ở index khác thấy ngay 102.

### 5.3. Conditional write cho invariant đơn khóa

Tồn kho:

~~~json
{
  "productId": "P100",
  "available": 1,
  "version": 12
}
~~~

Operation nguyên tử:

~~~text
IF available >= 1 AND version = 12:
    available = available - 1
    version = 13
ELSE:
    NOT_APPLIED
~~~

Hai client cạnh tranh cùng expected version 12 không thể cả hai thành công nếu hệ thực hiện đúng CAS trong cùng authority/scope.

**Bảo đảm nhận được:** invariant trên item được bảo vệ trước cạnh tranh cùng item.

**Chưa nhận được:** order record được tạo, payment được thực hiện, GSI/search đã cập nhật, region khác thấy item mới.

### 5.4. Per-key linearizability không tương đương multi-key atomicity

Giả sử tài khoản A và B lưu ở hai khóa, giao dịch chuyển 30:

~~~text
A.balance = 100
B.balance = 100
~~~

Hai mutation riêng:

~~~text
UPDATE A.balance -= 30
UPDATE B.balance += 30
~~~

Mỗi mutation có thể linearizable riêng, nhưng một reader có thể thấy:

~~~text
A.balance = 70
B.balance = 100
Total = 170
~~~

nếu đọc giữa hai bước. Invariant “tổng luôn 200” **không được bảo vệ** bởi tính đúng của từng khóa.

### 5.5. Lưu ý về delete và phiên bản

Một khóa bị xóa rồi tạo lại có thể gặp **ABA problem** nếu client chỉ so giá trị hiện tại. Nếu cần bảo vệ vòng đời, dùng generation/ETag/version hoặc tombstone theo mô hình được hỗ trợ.

Không được coi việc đọc `not found` tại replica có thể trễ là bằng chứng toàn cục rằng khóa chưa tồn tại để tạo duy nhất.

## 6. Phạm vi theo phân vùng (per-partition consistency)

### 6.1. Logical partition và physical partition

**Logical partition** thường là tập dữ liệu cùng giá trị partition key được xem là một đơn vị logic truy vấn/phân phối theo sản phẩm.

**Physical partition/shard** là đơn vị lưu trữ/điều phối trên hạ tầng. Một physical partition có thể chứa nhiều logical partitions; cách map có thể thay đổi khi scale.

Ví dụ:

~~~text
Logical partition key = customerId

Customer U42:
   Order O1
   Order O2
   Order O3
~~~

Nhưng không phải mọi hệ giữ nhiều order document cùng customer trong **một giao dịch** chỉ vì chúng cùng partition key. Phải có API/bảo đảm cụ thể.

### 6.2. Cùng partition chưa chắc cùng một atomic write

Một Cassandra partition chứa nhiều clustering rows. Điều đó làm việc đọc/ghi theo access pattern thuận lợi, nhưng không có nghĩa mọi `INSERT` rời trong partition tạo thành một transaction snapshot như SQL.

Tương tự, ở DynamoDB, nhiều item cùng partition key không tự động trở thành một item nguyên tử. Cơ chế conditional write trực tiếp bảo vệ item; transaction nhiều item dùng API riêng.

### 6.3. Thứ tự cục bộ

Một engine có thể bảo đảm thứ tự áp dụng mutation trong một partition, nhưng không có thứ tự tương đương giữa hai partition khác nhau.

~~~text
Partition P1:  A1 -> A2 -> A3
Partition P2:  B1 -> B2 -> B3
~~~

Không có căn cứ để suy một thứ tự toàn cục duy nhất:

~~~text
A1 -> B1 -> A2 -> B2 -> ...
~~~

trừ khi database hoặc ứng dụng cung cấp một cơ chế điều phối/transaction toàn cục rõ ràng.

### 6.4. Hot partition và consistency

Đưa tất cả bất biến vào một partition có thể giúp giảm phạm vi phối hợp, nhưng tăng contention:

- Nhiều writer cạnh tranh;
- Latency tăng;
- Throughput bị giới hạn bởi leader/replica của partition;
- Partition lớn khó bảo trì;
- Tác vụ khác bị ảnh hưởng bởi một khóa nóng.

Một thiết kế “mọi đơn của hệ trong một partition” có thể làm consistency dễ suy nghĩ hơn nhưng khó scale. Phải cân bằng tính đúng và ranh giới aggregate.

### 6.5. Transaction trong một logical partition

Một số hệ như Azure Cosmos DB for NoSQL hỗ trợ transactional batch trong cùng **logical partition key**, theo giới hạn dịch vụ. Đây là ví dụ **bảo đảm transaction có phạm vi ràng buộc bởi partition**, không phải mọi NoSQL cùng partition đều tự có batch atomicity.

## 7. Phạm vi theo giao dịch (transaction consistency/isolation)

### 7.1. Atomicity của nhiều thao tác

Một transaction lý tưởng cho chuyển tiền:

~~~text
BEGIN
  Debit(A, 30)
  Credit(B, 30)
COMMIT
~~~

Nếu một trong hai bước thất bại trước commit, transaction phải không công bố nửa kết quả theo hợp đồng atomicity.

Khi hệ hỗ trợ multi-document/multi-item transactions, phạm vi thực tế còn phụ thuộc:

- Những collection/table nào;
- Những partition/shard nào;
- Một hay nhiều region;
- Transaction timeout;
- Độ lớn/số lượng item;
- Isolation level;
- Cách xử lý retry và unknown commit.

### 7.2. Atomicity khác isolation

**Atomicity:** cả nhóm thay đổi được commit theo một đơn vị hoặc không.

**Isolation:** transaction khác được phép quan sát gì khi các transaction chạy đồng thời.

Một transaction có thể atomic nhưng người phát triển vẫn cần hiểu snapshot, serializable và hành vi conflict để bảo vệ bất biến.

### 7.3. Snapshot isolation

Một transaction đọc một ảnh chụp nhất quán theo thời điểm logic của nó, rồi áp dụng các write theo quy tắc conflict.

~~~text
Tx A đọc trạng thái S tại snapshot t1
Tx B cập nhật dữ liệu
Tx A vẫn có thể đọc dữ liệu theo snapshot t1
~~~

Snapshot isolation hữu ích để tránh **fractured reads** trong nhiều trường hợp, nhưng **không luôn ngăn write skew**.

### 7.4. Write skew dù từng bản ghi được CAS/ghi đúng

Quy tắc bệnh viện:

> Trong mỗi ca luôn có ít nhất một bác sĩ trực.

Dữ liệu:

~~~text
Doctor D1: onCall=true
Doctor D2: onCall=true
~~~

Transaction A đọc D1/D2, thấy D2 trực nên đặt `D1=false`. Transaction B cũng đọc D1/D2 trong snapshot khác, thấy D1 trực nên đặt `D2=false`.

Nếu hai transaction ghi **hai document khác nhau** và isolation chỉ chặn write-write conflicts trên cùng document, cả hai có thể commit:

~~~text
D1=false
D2=false
~~~

Đây là write skew. Để bảo vệ invariant tập hợp, có thể cần **serializable isolation**, một aggregate có điều kiện nguyên tử hoặc lock/authority chung.

### 7.5. Serializability và strict serializability

**Serializability** yêu cầu kết quả transaction tương đương một thứ tự tuần tự hợp lệ. **Strict serializability** bổ sung yêu cầu phù hợp thứ tự thời gian thực giữa các transaction hoàn tất, là một bảo đảm mạnh hơn.

Không nên nhầm:

- Linearizable update một document;
- Serializable transaction nhiều document;
- Causal reads trong session.

Chúng trả lời các câu hỏi khác nhau và có thể được hỗ trợ với những phạm vi khác nhau.

### 7.6. Snapshot của transaction không áp dụng cho mọi thời điểm đọc

Một transaction kết thúc, rồi client đọc qua cache, search index hoặc vùng địa lý khác: read đó không mặc nhiên dùng **snapshot cũ** hay bảo đảm của transaction đã kết thúc.

Bất kỳ hợp đồng nào về quan sát sau commit đều phải nêu **đường đọc**.

## 8. Phạm vi theo phiên (session consistency)

### 8.1. Phiên logic là gì?

Một session có thể là một chuỗi operation trên SDK connection, một client object hoặc một phiên logic có token riêng — tùy sản phẩm.

Ví dụ:

~~~text
Mobile client U42
    |
    +--> Write profile: language="en"
    |
    +--> Read profile tại region/replica khác
~~~

Người dùng mong vừa lưu ngôn ngữ “en” thì màn hình reload vẫn thấy “en”, dù một người khác có thể đọc replica chưa cập nhật.

Đó là trường hợp quan trọng của **read-your-writes**.

### 8.2. Read-your-writes (RYW)

Sau khi một phiên ghi `K=v2` thành công, những lần đọc K sau đó trong **cùng phiên** phải nhìn thấy v2 hoặc một trạng thái đủ mới theo ngữ nghĩa của hệ.

~~~text
Session S:
  PUT K=v2 -> success
  GET K    -> v2 (hoặc bản mới hơn hợp lệ)
~~~

RYW không buộc mọi session khác nhìn v2 ngay lập tức.

### 8.3. Monotonic reads (MR)

Nếu trong một phiên đã đọc bản v5, phiên không được đọc lùi về v3 trong những lần đọc sau theo quy tắc của model.

~~~text
Session S:
  GET K -> v5
  GET K -> v6
  GET K -> v4   // Vi phạm monotonic reads nếu chưa có ngữ nghĩa khác
~~~

Đặc biệt quan trọng khi client đổi replica hoặc region.

### 8.4. Monotonic writes (MW)

Các ghi do **cùng một phiên** phát ra phải được áp dụng theo đúng thứ tự cần giữ:

~~~text
Session S:
  PUT profile.status="STARTED"
  PUT profile.status="COMPLETED"
~~~

Một replica không được áp dụng ghi “COMPLETED” rồi nhận ghi “STARTED” cũ theo cách làm trạng thái đi ngược khi contract yêu cầu monotonic writes.

### 8.5. Writes-follow-reads (WFR)

Nếu phiên đã đọc một trạng thái, những ghi tiếp theo có phụ thuộc vào trạng thái đó phải được đặt **sau các ghi đã tạo trạng thái được đọc** trong thứ tự nhân quả.

Ví dụ:

~~~text
Session B:
  READ post P
  WRITE comment C trả lời P
~~~

C có phụ thuộc vào P. WFR giúp bảo tồn quan hệ “đã nhìn P rồi mới ghi C” theo phạm vi và điều kiện của model.

### 8.6. Session token / causal metadata

Để giữ các bảo đảm trên khi đi qua replica hoặc region khác, SDK/service có thể gắn token thể hiện:

- Version hoặc log position đã thấy;
- Causal dependency;
- Session progress;
- Partition progress.

Client hoặc backend cần mang token đúng giữa các request. Nếu mỗi HTTP request tạo một database client mới rồi bỏ session metadata, bảo đảm **có thể bị mất dù SDK hỗ trợ session consistency**.

### 8.7. Session không phải user account vô thời hạn

Một người đăng nhập cùng tài khoản trên điện thoại và laptop chưa chắc hai thiết bị đang chia sẻ database session token.

Nếu muốn “thay đổi của thiết bị A hiện trên thiết bị B ngay”, không được chỉ viện dẫn RYW của A. Cần xét hợp đồng liên thiết bị, propagation, synchronization và read routing.

### 8.8. Causal consistency không tạo transaction đa bản ghi

Một session có thể thấy các thao tác theo thứ tự nhân quả nhưng vẫn đọc trạng thái mà hai khóa đã được update qua hai operation riêng, không cùng commit.

Ví dụ “cập nhật Order rồi cập nhật Inventory” có thể bảo tồn thứ tự, nhưng vẫn có khoảng thời gian người đọc thấy Order mới và Inventory cũ. Causal ordering **không đồng nghĩa atomicity**.

## 9. Phạm vi theo vùng triển khai (region consistency)

### 9.1. Một region có nhiều replica

Một region vật lý có thể gồm nhiều availability zones và replica:

~~~text
Region A
  ├── AZ1 / Replica A1
  ├── AZ2 / Replica A2
  └── AZ3 / Replica A3
~~~

Sản phẩm có thể cung cấp strongly consistent read hoặc quorum write **trong region**, nhưng không vì vậy mà một region khác cũng đọc thấy ngay.

### 9.2. Sao chép liên vùng

~~~text
       Region A                      Region B
     +----------+                  +----------+
     | Replica  | -- async log --> | Replica  |
     | A        |                  | B        |
     +----------+                  +----------+
        ^
        |
   Client writes
~~~

Ở T1, A xác nhận ghi v2; B vẫn có v1 do network/replication lag. Một client đọc B tại T2 có thể thấy v1 nếu mô hình triển khai cho phép stale reads.

**Vì vậy, “đã ghi thành công” phải được hiểu cùng với write acknowledgement scope.**

### 9.3. Single-writer region

Một mô hình tập trung writes về region A:

- Dễ có một authority cho thứ tự ghi.
- Region B có thể nhận replication bất đồng bộ.
- Đọc ở B có thể bị trễ.
- Khi A lỗi, failover cần quyết định mốc commit và trạng thái đã sao chép.

Nếu yêu cầu read-your-writes xuyên region, có thể cần route read về A, đợi replication hoặc mang token để chọn replica đã bắt kịp.

### 9.4. Multi-writer region

Nếu A và B cùng chấp nhận ghi:

~~~text
Region A: UPDATE K -> vA
Region B: UPDATE K -> vB
~~~

phải có quy tắc **conflict detection/resolution** hoặc một giao thức điều phối trước commit.

Những chính sách có thể gồm:

- Một region/leader có quyền cho key;
- Consensus/quorum xuyên region;
- Last-writer-wins theo timestamp/metadata;
- Merge theo CRDT;
- Application-level conflict resolution;
- Reject một số thao tác.

**Last-writer-wins không tự giữ invariant nghiệp vụ** như tồn kho không âm hoặc username duy nhất. Hai region có thể từng trả thành công cho hai claim xung đột trước khi một giá trị bị chọn làm “winner”.

### 9.5. Replication bất đồng bộ và durability

Một write được xác nhận ở region A có thể đã **durable trong A** nhưng chưa tồn tại ở B. Nếu cả A không phục hồi và chưa kịp replicate, việc chuyển sang B có thể mất một phần thay đổi đã xác nhận theo mô hình RPO được thiết kế.

Đó là câu hỏi **durability/disaster recovery** liên quan nhưng không trùng consistency read. Cần phân biệt:

- Đọc có nhìn trạng thái mới không?
- Sau failover, ghi đã xác nhận có còn không?
- Có thể mất bao nhiêu dữ liệu (RPO)?
- Khả năng phục hồi mất bao lâu (RTO)?

Không nên dùng tên “strong” mà bỏ qua phạm vi vùng và failure model.

## 10. Một sơ đồ tổng hợp năm lớp bảo đảm

~~~text
                       Client session S1
                              |
                     causal/session token
                              |
                              v
                  +-----------------------+
                  | Region A              |
                  |                       |
                  | Partition P1          |        Region B
                  |  K1, K2, K3           |        +-------------+
                  |  key-level operations | --rep-> | replicas    |
                  |                       |        | stale/fresh  |
                  | Partition P2          |        +-------------+
                  |  K4, K5               |
                  |                       |
                  | Transaction boundary  |
                  |  {K1, K4}? Depends    |
                  |  on database/API       |
                  +-----------------------+
                              |
                              v
                     Search / cache view
                   (separate propagation)
~~~

Mỗi đường biên trên có câu hỏi riêng:

1. **Key:** `K1` có được cập nhật nguyên tử?
2. **Partition:** `K1,K2,K3` có cùng thứ tự/transaction guarantee nào?
3. **Transaction:** `K1,K4` có thể cùng commit không?
4. **Session:** sau khi ghi K1, S1 có đọc lại thấy kết quả không?
5. **Region:** S2 ở B khi nào thấy K1?
6. **Projection:** search/cache có phản ánh K1 hay chưa?

Một feature chỉ đúng khi những đường biên mà invariant vượt qua đều được thiết kế.

## 11. Những lỗi quan sát hay gặp khi phạm vi bị hiểu nhầm

### 11.1. Stale read

~~~text
PUT K=v2 -> success tại leader
GET K tại replica chậm -> v1
~~~

Người dùng vừa sửa hồ sơ nhưng thấy dữ liệu cũ.

### 11.2. Read skew / fractured read

Giả sử một transfer update hai key A, B; reader không có snapshot đa key có thể thấy một trạng thái từ trước và một từ sau:

~~~text
Read A.balance -> 70
Read B.balance -> 100
~~~

Nếu kỳ vọng tổng bằng 200 tại một thời điểm nhất quán, kết quả này là sai theo hợp đồng báo cáo, dù mỗi key riêng lẻ được đọc hợp lệ.

### 11.3. Lost update

Hai client cùng đọc v7 và ghi dựa vào snapshot v7, một ghi đè kết quả của client kia. Cần CAS/version/transaction tương ứng.

### 11.4. Write skew

Hai transaction dựa trên snapshot về hai bản ghi và ghi vào hai bản ghi khác nhau, làm invariant tập hợp sai. Snapshot isolation không nhất thiết ngăn; cần serializable hoặc authority chung.

### 11.5. Read-your-writes violation

Session S ghi v2 thành công, rồi đọc v1 dù đã yêu cầu RYW. Có thể do token không được mang tiếp hoặc đường read không thuộc phạm vi bảo đảm.

### 11.6. Monotonic-read violation

Session đọc v5 rồi v4 khi chuyển vùng, dù không có ghi đảo trạng thái hợp lệ.

### 11.7. Non-repeatable read

Cùng transaction/luồng đọc một row hai lần và thấy hai giá trị khác nhau. Có thể hợp lệ hoặc không tùy isolation level. Không nên mặc định mọi transaction có repeatable reads.

### 11.8. Phantom read

Transaction đọc tập bản ghi theo predicate, sau một mutation concurrent, đọc lại predicate thấy thêm/bớt bản ghi. Khả năng ngăn phantom phụ thuộc isolation và index/locking protocol; per-key atomicity không đủ.

## 12. DynamoDB: phân biệt item, transaction, index và region

Amazon DynamoDB là ví dụ rõ về việc **một sản phẩm có nhiều loại đường đọc với phạm vi consistency khác nhau**.

### 12.1. Một item

DynamoDB hỗ trợ conditional writes trên item, ví dụ:

~~~json
{
  "TableName": "Inventory",
  "Key": {
    "PK": {"S": "PRODUCT#P100"}
  },
  "ConditionExpression": "#a >= :one",
  "UpdateExpression": "SET #a = #a - :one",
  "ExpressionAttributeNames": {
    "#a": "available"
  },
  "ExpressionAttributeValues": {
    ":one": {"N": "1"}
  }
}
~~~

Condition được đánh giá khi update được thực thi trong phạm vi item. Điều này bảo vệ invariant một item nhưng không commit cùng một order item khác.

### 12.2. Read consistency của bảng/index

Với API và cấu hình được hỗ trợ:

- Đọc bảng cơ sở có thể chọn eventually consistent hoặc strongly consistent read trong phạm vi dịch vụ.
- Local secondary index có những lựa chọn mạnh phù hợp với bảng cơ sở.
- Global secondary index (GSI) có đường sao chép/indexing riêng và **không hỗ trợ strongly consistent reads theo cách đọc bảng cơ sở**.
- DynamoDB Streams có semantics riêng, không phải snapshot của thao tác GET.

Ví dụ một item nguồn đã đổi status nhưng GSI theo status còn chậm: query qua GSI có thể chưa phản ánh cập nhật. Không được lấy kết quả GSI ngay sau write làm chứng cứ tuyệt đối rằng mutation chưa xảy ra.

### 12.3. TransactWriteItems và TransactGetItems

DynamoDB có các API transaction nhiều item, với giới hạn số item, kích thước và phạm vi hỗ trợ. Đó là bảo đảm **multi-item transaction**, khác một conditional update item đơn.

Không nên giả định một transaction đơn vùng tự bao gồm các bản sao của global table ở region khác trong cùng atomic commit.

### 12.4. Global tables

Global tables có cấu hình/tính năng sao chép và nhất quán phụ thuộc loại bảng, chế độ triển khai, vùng hỗ trợ và phiên bản dịch vụ. Không nên gắn một quy tắc “mọi global table luôn eventual” hoặc “mọi global table luôn strong” cho tất cả cấu hình hiện đại.

Với multi-region writes, cần kiểm tra chính xác chế độ replication/consistency được bật, hành vi conflicts và việc transaction được nhìn thấy sau replication. **Single-item conditional success tại một region không tự chứng minh uniqueness xuyên các vùng nếu cấu hình còn có ghi đồng thời và conflict resolution riêng.**

### 12.5. Thiết kế đúng với một đơn hàng

Nếu phải tạo Order và giảm Inventory cùng lúc, hãy cân nhắc transaction phù hợp hoặc reservation ledger có idempotency. Nếu chỉ cần đọc Order vừa tạo, có thể dùng đường đọc mạnh được hỗ trợ hoặc session/read routing phù hợp; query GSI không nên được hứa tức thì nếu index còn eventual.

## 13. Cassandra: consistency level và phạm vi replica

Apache Cassandra thường cho phép chọn **consistency level** ở từng request đọc/ghi trong một topology cụ thể.

### 13.1. ONE, QUORUM, ALL

Với replication factor = 3 trong một data center, mô hình trực giác:

| Consistency level | Ý nghĩa khái quát |
|---|---|
| ONE | Cần phản hồi từ một replica phù hợp |
| QUORUM | Cần đa số replica phù hợp trong phạm vi tính quorum |
| ALL | Cần mọi replica thuộc phạm vi yêu cầu phản hồi |
| LOCAL_QUORUM | Quorum trong data center cục bộ theo cấu hình replication |
| EACH_QUORUM | Quorum của từng data center theo semantics hỗ trợ |
| SERIAL/LOCAL_SERIAL | Serial consistency gắn với LWT/Paxos trong phạm vi tương ứng |

Đây là mô hình khái niệm, không thay thế tài liệu về replication strategy, pending replicas, transient replication, failure và phiên bản Cassandra.

### 13.2. Quy tắc giao nhau của quorum

Một heuristic quen thuộc:

\[
R + W > RF
\]

Trong mô hình replica đơn giản, nếu số replica đọc R và ghi W cộng lại lớn hơn replication factor RF, hai tập replica phải có giao nhau.

Ví dụ RF=3, R=2, W=2:

~~~text
Write acknowledged by A, B
Read queries B, C
Intersection = B
~~~

Giao nhau giúp tăng cơ hội đọc có thông tin mới, nhưng **không tự chứng minh linearizability mạnh trên mọi history**. Còn phải xét timestamp reconciliation, simultaneous writes, clock skew, failures, stale replica, tombstones, LWT và lựa chọn read path.

### 13.3. LWT và regular write khác nhau

Cassandra dùng LWT với `IF` để thực hiện conditional mutations theo một giao thức đồng thuận trong phạm vi được hỗ trợ:

~~~sql
UPDATE reservations_by_id
SET state = 'CONFIRMED',
    version = 8
WHERE reservation_id = 'R100'
IF state = 'PENDING' AND version = 7;
~~~

LWT có độ trễ và conflict semantics khác regular write; không phải cứ đặt CL=QUORUM cho regular write là tương đương CAS. Cũng không được coi một LWT trên một partition là transaction nguyên tử xuyên nhiều partition khác.

### 13.4. Multi-DC và LOCAL_QUORUM

Nếu một cluster có data center A/B, `LOCAL_QUORUM` của client ở A chỉ yêu cầu quorum trong A theo topology phù hợp. Điều đó không tự cam kết tất cả replica B đã nhận mutation.

Khi client đổi region/DC rồi đọc tại B, có thể thấy khác biệt nếu replication chưa bắt kịp và hợp đồng read không buộc nó đợi.

### 13.5. Repair và tombstone

Một write đã được quorum xác nhận không chứng minh mọi replica đã biết xóa. Nếu replica offline lâu hơn thời gian bảo vệ tombstone và repair không hoàn tất, có rủi ro dữ liệu cũ hồi sinh trong điều kiện nhất định.

Vì vậy consistency level mỗi request không thay thế **anti-entropy repair, chính sách tombstone và vận hành node**.

### 13.6. Materialized views và bảng phi chuẩn hóa

Một ứng dụng Cassandra thường tự tạo nhiều bảng cho các access pattern. Cập nhật bảng nguồn và bảng đọc theo một request không mặc định là **transaction ACID toàn bộ read models**. Phải thiết kế idempotency, event propagation và reconciliation.

## 14. MongoDB: read concern, write concern và session/transaction

MongoDB có nhiều điều khiển khác nhau:

- **Write concern**: mức xác nhận write;
- **Read concern**: tính chất snapshot/đọc được chọn;
- **Read preference**: chọn primary/secondary để đọc;
- **Client session**: bối cảnh cho causal consistency/transactions;
- **Multi-document transaction**: nhóm thao tác trong phạm vi được hỗ trợ.

### 14.1. Một document được cập nhật nguyên tử

~~~javascript
db.inventory.updateOne(
  {
    _id: "P100",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
~~~

Filter và update được thực hiện nguyên tử với document phù hợp. Không vì thế mà một document Order khác cũng được tạo nguyên tử.

### 14.2. Write concern majority không có nghĩa mọi read đều mới nhất

Một write với majority acknowledgement có ý nghĩa về số bản sao xác nhận theo hợp đồng write concern. Nếu sau đó client đọc secondary bằng read preference/concern không phù hợp, **không nên mặc định** read sẽ có semantics của một linearizable primary read.

Tương tự, `readConcern: "majority"` không đồng nghĩa một phép đọc toàn hệ có thứ tự thời gian thực như `linearizable`. Mỗi concern giải quyết một điều kiện cụ thể.

### 14.3. Causally consistent session

Khi cấu hình và dùng đúng các read/write concerns tương ứng (thường cần `majority` cho bảo đảm nhân quả được tài liệu MongoDB mô tả), causal session giúp duy trì những quan hệ như:

- Read-your-writes;
- Monotonic reads;
- Monotonic writes;
- Writes-follow-reads.

Điều này phụ thuộc việc **dùng cùng session/lan truyền causal metadata**, không chỉ dùng cùng userId.

### 14.4. Snapshot transaction

MongoDB hỗ trợ multi-document transactions trong những topology phù hợp, với read concern, write concern và commit semantics riêng. Khi đọc nhiều document phải có snapshot tương thích, cần transaction tương ứng thay vì nhiều `findOne()` riêng lẻ và hy vọng cùng mốc.

Một transaction phải được giữ ngắn, và khi commit không chắc chắn cần tuân thủ cơ chế retry/unknown commit của driver. Không dùng transaction kéo dài trong lúc chờ API thanh toán.

### 14.5. Đọc qua cache hoặc search không kế thừa session

Nếu sau khi commit MongoDB, ứng dụng đọc từ Redis hoặc Elasticsearch/OpenSearch, causal session của MongoDB **không tự đi theo**. Muốn UX ổn định, API phải kiểm tra freshness/version ở từng read model hoặc tạm đọc nguồn.

## 15. Azure Cosmos DB for NoSQL: năm mô hình và các phạm vi khác nhau

Azure Cosmos DB for NoSQL thường mô tả năm mức consistency:

1. Strong;
2. Bounded staleness;
3. Session;
4. Consistent prefix;
5. Eventual.

Điều quan trọng là hiểu các bảo đảm này theo **cấu hình account, vùng, session và loại operation được dịch vụ hỗ trợ**, thay vì suy từ tên mức ra transaction đa item ở mọi partition.

### 15.1. Strong

Mô hình strong nhằm cung cấp trải nghiệm đọc trạng thái mới nhất theo hợp đồng trong phạm vi hỗ trợ, đổi lại có yêu cầu phối hợp, độ trễ hoặc ràng buộc triển khai. Không tự suy rằng mọi API đa vùng với mọi cấu hình đều được phép bật strong theo đúng mong muốn; cần kiểm tra vùng và chế độ replication thực tế.

### 15.2. Bounded staleness

Bảo đảm độ trễ nhất định theo số phiên bản hoặc thời gian trong các điều kiện dịch vụ quy định. Điều này có thể hữu ích khi muốn trade-off giữa tính mới và latency với **ngưỡng có nghĩa**, nhưng không nên bỏ qua hành vi khi bound không thể đáp ứng do partition mạng.

### 15.3. Session

Thông thường là lựa chọn phù hợp khi muốn chính client thấy ghi của mình, đồng thời cho phép các session khác đọc một replica có thể chậm hơn. Session token cần được quản lý qua request/các SDK instance theo thiết kế.

### 15.4. Consistent prefix và eventual

Hai mô hình yếu hơn về độ mới/thứ tự, thường được dùng khi application chấp nhận propagation lag và ưu tiên performance/availability. **Không nên quy cả hai thành “tùy ý trả gì cũng được”**; prefix còn có hợp đồng thứ tự riêng.

### 15.5. Transactional batch theo logical partition

Cosmos DB for NoSQL có transactional batch và một số cơ chế thực thi giao dịch trong phạm vi **cùng logical partition key**, không tự áp dụng nguyên tử qua mọi partition.

Tách hai câu hỏi:

- Client đọc dữ liệu với consistency nào?
- Những write nào nằm trong **cùng transaction boundary**?

Đổi consistency level không tự mở rộng boundary của transactional batch.

### 15.6. Session token không chứng minh mọi vùng bắt kịp

Nếu hai client/SDK không dùng cùng session token hoặc đọc qua đường khác, một client có thể còn thấy trạng thái cũ theo cấu hình session. Bảo đảm của **phiên** không trở thành bảo đảm của tất cả độc giả toàn cầu.

## 16. Firestore: đọc mạnh, transaction và phạm vi document

Cloud Firestore có các bảo đảm về consistency của document/query reads và transactions theo mô hình dịch vụ. Các transaction có thể cung cấp **serializable isolation theo commit time** trong điều kiện sản phẩm hỗ trợ.

### 16.1. Đọc và ghi document

Một document path:

~~~text
inventory/P100
~~~

có thể được cập nhật thông qua SDK với precondition hoặc transaction để tránh lost update.

Ví dụ mô hình:

~~~javascript
const ref = db.collection("inventory").doc("P100");

await db.runTransaction(async (tx) => {
  const snapshot = await tx.get(ref);
  if (!snapshot.exists) {
    throw new Error("NOT_FOUND");
  }

  const available = snapshot.get("available");
  if (available < 1) {
    throw new Error("OUT_OF_STOCK");
  }

  tx.update(ref, { available: available - 1 });
});
~~~

Các transaction callbacks có thể được retry, nên không gọi API thanh toán hoặc gửi email trực tiếp trong callback.

### 16.2. Transaction scope khác session scope

Một transaction chứa nhiều reads/writes theo giới hạn dịch vụ có thể bảo vệ một invariant rộng hơn update một document. Nhưng sau khi transaction commit, search/export/cache ở hệ ngoài Firestore không tự thuộc cùng transaction.

### 16.3. Chế độ concurrency và SDK

Firestore có những cơ chế optimistic/pessimistic concurrency khác nhau theo edition/cấu hình và loại SDK (mobile/web so với server). Không suy rằng “một transaction đọc document là mọi reader khác bị khóa” trong mọi trường hợp.

### 16.4. Multi-region location

Việc chọn location multi-region ảnh hưởng cách dịch vụ phân bố/nhân bản và đặc tính availability/latency; không nên coi đây là lý do để bỏ qua giới hạn transaction hoặc đường truy xuất ngoài dịch vụ. Các bảo đảm chi tiết cần lấy từ đúng edition, SDK và cấu hình đang dùng.

## 17. Redis: atomic command ở một key không phải consistency đa vùng

Redis thường cho phép một lệnh như `INCR` thực thi nguyên tử trên key trong phạm vi instance/cluster semantics tương ứng.

~~~redis
INCR counter:page:A
~~~

Nhưng một hệ Redis có primary/replica, replication và failover riêng:

- Client ghi thành công ở primary.
- Replica có thể chưa nhận update.
- Đọc replica có thể thấy giá trị cũ.
- Failover trước khi một mutation được sao chép đủ có thể tạo tình huống mất write theo mô hình cấu hình.

### 17.1. WAIT không tự làm mọi thứ linearizable

Redis có công cụ chờ số replica xác nhận đã nhận write trong những điều kiện nhất định. Nhưng nó không tự biến Redis thành một hệ transaction đồng thuận bền vững cho mọi write xuyên failover.

Phải phân biệt **replica nhận**, **replica bền vững trên disk**, **failover giữ được commit** và **đọc thấy đúng phiên bản**.

### 17.2. Redis Cluster và multi-key

Hai key ở hai hash slots có thể thuộc các shard khác nhau. Không được mặc định Lua/MULTI trên một node tạo transaction nguyên tử đa shard.

Nếu dùng Redis làm distributed lock bảo vệ MongoDB/Cassandra, mọi writer phải tuân thủ lock hoặc sink phải kiểm tra fencing; Redis command atomicity không tự cưỡng chế các write ở hệ khác.

## 18. Search index và read models: phạm vi nhất quán ngoài database nguồn

### 18.1. Search refresh

Elasticsearch/OpenSearch thường có khái niệm **near-real-time search**: document đã được index/write acknowledged nhưng truy vấn `_search` có thể cần refresh trước khi thấy.

~~~text
Source Write -> Search index update acknowledged
                          |
                          | refresh interval
                          v
                       Search visible
~~~

Một GET theo ID hoặc API đặc biệt có thể có semantics visibility khác với `_search`. Không được dùng một phép kiểm tra tìm kiếm chưa thấy để kết luận document không được ghi.

### 18.2. Read model qua CDC/outbox

~~~text
Orders DB
   |
   +--> OrderByCustomer projection
   |
   +--> Search index
   |
   +--> Analytics
~~~

Các projection có thể ở các mốc khác nhau:

~~~text
Orders DB        : Order O100 version=12
OrderByCustomer  : version=11
Search           : version=10
Analytics        : batch gần nhất
~~~

Dù source có transaction mạnh, read model vẫn phải có freshness contract riêng.

### 18.3. Dùng version/checkpoint để thể hiện freshness

Một API có thể lưu:

~~~json
{
  "orderId": "O100",
  "sourceVersion": 12,
  "status": "PAID"
}
~~~

Ở projection:

~~~json
{
  "orderId": "O100",
  "sourceVersion": 11,
  "status": "CREATED"
}
~~~

Client/backend có thể phát hiện projection chậm nếu biết version mong muốn. Tuy nhiên, **version trên từng item không tự tạo snapshot của cả một danh sách**; nếu cần toàn cục, cần checkpoint/snapshot semantics phù hợp.

### 18.4. Không dùng consistency của source để hứa cho cache

Nếu Redis cache được cập nhật sau MongoDB, việc MongoDB trả readConcern mạnh không ngăn Redis trả dữ liệu cũ. Cần cache invalidation, versioned keys, bypass cache sau write, TTL hoặc token/consistency protocol ở lớp ứng dụng.

## 19. Chọn mức đọc không đồng nghĩa chọn đúng nơi đọc

Một API có thể có tham số “strong read”, nhưng nếu cuối cùng query lại đi qua:

~~~text
API -> Redis cache -> Search -> Data source
~~~

thì cần biết tầng nào thực sự thực hiện đọc:

- Redis có key cũ không?
- Search đã refresh chưa?
- API có bypass read model không?
- Client có mang session token không?
- Có route về authority phù hợp không?

**Consistency là bảo đảm end-to-end của đường đọc mà user thật sự trải nghiệm**, không chỉ là một option ở driver nằm sâu bên trong.

## 20. Phân trang không tự mang một snapshot

Giả sử user duyệt danh sách đơn mới nhất:

~~~text
Page 1: O105, O104
Page 2: O103, O102
~~~

Nếu dùng offset và có đơn mới, phần tử có thể lặp hoặc bị bỏ sót do vị trí dịch.

Dùng keyset/continuation token có thể giảm một số vấn đề dịch vị trí, nhưng **không tự tạo snapshot** của cả tập kết quả:

- Record mới có timestamp cũ vẫn có thể vào trang sau.
- Một record đổi sort key có thể bị lặp hoặc bỏ sót.
- Token của database có thể chỉ là vị trí tiếp tục, không phải snapshot ID.

Nếu cần xuất đúng tập dữ liệu tại một mốc, phải dùng snapshot/PIT/transaction/export protocol được engine hỗ trợ hoặc một data cut có version rõ ràng.

## 21. Quorum intersection không tự thay giao dịch đa khóa

Một lỗi thiết kế:

> “Chúng tôi dùng QUORUM cho tất cả writes và reads nên chuyển tiền giữa hai tài khoản là ACID.”

Quorum cho từng operation giúp điều phối replica trong phạm vi tương ứng, nhưng hai mutation:

~~~text
Debit(A)
Credit(B)
~~~

vẫn có thể bị ngắt bởi crash giữa hai bước. Atomicity của transfer không được suy từ R+W>RF.

Tương tự:

- MongoDB majority writes không tự gom hai `updateOne()` thành transaction.
- DynamoDB strong reads không tự nối hai conditional writes rời.
- Cosmos session consistency không tự tạo multi-partition transaction.
- Redis lệnh nguyên tử trên từng key không tự bảo vệ transaction nhiều shard.

**Đường biên bảo đảm phải bao trùm toàn bộ invariant.**

## 22. Session consistency và API web có nhiều request

### 22.1. Web API stateless

Mỗi HTTP request có thể đến một pod khác:

~~~text
Browser
  |
  +--> POST /profile  -> Pod A -> DB client session SA
  |
  +--> GET /profile   -> Pod B -> DB client session SB
~~~

Nếu DB session chỉ nằm trong memory của Pod A, Pod B có thể không biết write mới nhất mà user cần thấy.

### 22.2. Ba hướng thiết kế

1. **Sticky routing/session:** giữ các request phù hợp với một context, nhưng phải xét failover và scale.
2. **Session token propagation:** API trả token mà client gửi lại; backend xác thực và chuyển vào database SDK theo hợp đồng.
3. **Read from authority sau write:** các request cần độ mới cao được route tới leader/strong read phù hợp.

Mỗi hướng có chi phí và giới hạn. Sticky routing không tự giải quyết read model stale; token không thể dùng cho engine khác nếu không có protocol tích hợp.

### 22.3. Hợp đồng API minh họa

Response sau khi cập nhật:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "profile": {
    "userId": "U42",
    "language": "en",
    "version": 13
  },
  "consistencyToken": "opaque-token"
}
~~~

Request đọc tiếp:

~~~http
GET /api/profiles/U42
X-Consistency-Token: opaque-token
~~~

Backend có thể dùng token để yêu cầu mốc đọc tối thiểu hoặc route đúng nơi, **chỉ nếu có khả năng thực thi điều đó**. Không nên phát header trang trí rồi hứa RYW nếu database/API không thể bảo đảm.

### 22.4. Token cần ràng buộc quyền/ngữ cảnh

Nếu token chứa mốc session/region/partition, không nên tự tin nó là credential. API vẫn phải xác thực người dùng và tenant, giới hạn token size, phiên bản, thời hạn và phạm vi sử dụng.

Một token cho tenant T1 không được tự động dùng để đọc dữ liệu tenant T2.

## 23. Multi-region, latency và availability

### 23.1. Độ trễ vật lý không biến mất

Nếu một write tại Việt Nam phải đợi quorum ở những region cách xa, thời gian vòng đi/về mạng gây latency đáng kể.

Vì vậy một thiết kế có thể ưu tiên:

- Strong consistency trong region;
- Session/causal guarantees cho client;
- Async replication sang region khác;
- Strong global coordination cho số ít operation quan trọng.

Không có một lựa chọn tốt nhất cho mọi dữ liệu.

### 23.2. Khi network partition

Nếu network giữa region A và B bị chia cắt:

- Một hệ ưu tiên consistency mạnh toàn cục có thể phải từ chối một số reads/writes để tránh hai authority đồng thời.
- Một hệ ưu tiên availability cục bộ có thể tiếp tục nhận writes rồi giải quyết conflict về sau.
- Một hệ dùng session token có thể phải **đợi** hoặc báo lỗi khi replica chưa đáp ứng mốc session.

Đây là đánh đổi về consistency, availability và latency khi có lỗi mạng; không nên giản lược thành “NoSQL là AP, SQL là CP”.

### 23.3. CAP và PACELC là công cụ tư duy, không phải nhãn sản phẩm cố định

CAP nêu một ràng buộc về việc cung cấp consistency và availability khi mạng có phân hoạch theo một mô hình lý thuyết. PACELC nhấn mạnh cả đánh đổi latency/consistency khi không có partition.

Không nên gắn nhãn cho toàn bộ database mà không hỏi:

- Operation nào?
- Key nào?
- Read/write concern nào?
- Region/topology nào?
- Failure model nào?
- Availability được định nghĩa là response hợp lệ hay luôn chấp nhận write?

Một sản phẩm có thể cung cấp nhiều cấu hình và nhiều API với đánh đổi khác nhau.

## 24. Kịch bản: cập nhật hồ sơ trên hai thiết bị

Người dùng U42 dùng điện thoại và laptop.

~~~text
T0 Phone: đổi language=ja, được xác nhận
T1 Phone: reload màn hình
T2 Laptop: refresh hồ sơ
~~~

### 24.1. Yêu cầu chỉ RYW

Nếu sản phẩm chỉ yêu cầu điện thoại không nhìn dữ liệu lùi sau khi lưu, **session consistency** trên phone có thể đủ. Laptop có thể thấy bản cũ tạm thời theo contract và UI cần thông báo phù hợp.

### 24.2. Yêu cầu cả hai thiết bị lập tức thấy mới

Lúc này RYW của một session **không đủ**. Cần đường đọc strong/global theo phạm vi được hỗ trợ, push invalidation, synchronization hoặc mốc phiên bản được chia sẻ; xác định SLA rõ ràng.

### 24.3. Yêu cầu sửa đồng thời không mất dữ liệu

Phone đổi language, laptop đổi timezone dựa trên cùng snapshot. Cần version/ETag, patch field độc lập hoặc conflict resolution phù hợp để tránh lost update. RYW không tự chặn lost update giữa hai thiết bị.

## 25. Kịch bản: giỏ hàng, đặt hàng và tồn kho

### 25.1. Bất biến per-item

~~~text
available(P100) >= 0
~~~

Dùng conditional decrement tại nguồn inventory.

### 25.2. Bất biến multi-item

~~~text
Nếu order được xác nhận, inventory đã được giữ và
reservation thuộc đúng order đó.
~~~

Nếu inventory và order ở hai item, cần transaction có phạm vi phù hợp hoặc workflow reservation/idempotency/compensation.

### 25.3. Trải nghiệm một session

Sau khi đặt hàng, người dùng mong “Đơn hàng của tôi” hiển thị O100. Nếu danh sách đơn là projection async, API có thể:

- Trả trực tiếp đơn O100 từ response create;
- Đọc nguồn authoritative sau create;
- Mang version/token để đợi projection đạt mốc;
- Hiển thị trạng thái “đang đồng bộ” trong giới hạn SLO.

Không được hứa RYW của projection chỉ vì source write thành công.

### 25.4. Khách ở region khác

Nhân viên CSKH ở region B có thể chưa thấy đơn mới nếu hệ dùng async replication. Cần xác định liệu nghiệp vụ cho phép staleness vài giây hay phải route read đến nguồn.

## 26. Kịch bản: tài khoản và số dư

Một ứng dụng tài chính cần bảo vệ số dư và bút toán:

~~~text
Account A -> debit 30
Account B -> credit 30
Ledger L -> record transfer
~~~

Bảo đảm mong muốn có thể bao gồm:

- Không cho số dư âm nếu đó là rule;
- Không tạo hai transfer cho một idempotency key;
- Không mất một vế chuyển tiền;
- Audit trail bền vững;
- Không trả tổng số dư từ các phiên bản không tương ứng.

Nếu dùng ba conditional writes rời, **mỗi write có thể đúng trên key của nó nhưng toàn workflow sai** khi crash giữa chừng.

Cần chọn transaction/ledger design hoặc saga có trạng thái bù rõ ràng. Nếu phải phục vụ báo cáo “tổng số dư tại thời điểm T”, còn cần snapshot/read consistency tương ứng.

Không nên đánh đồng “tất cả item có consistent read” với “một lần đọc nhiều item có snapshot chung”.

## 27. Kịch bản: phiên đăng nhập và quyền truy cập

Giả sử người quản trị thu hồi quyền của user U42 tại T0. Session ở region khác vẫn dùng cache ACL cũ.

Đây không chỉ là UX:

- Nếu chấp nhận quyền cũ sau revoke, có thể là rủi ro bảo mật.
- Nếu chỉ dùng session consistency của user U42, nó không chắc thấy thay đổi từ admin session.
- Nếu ACL read model bất đồng bộ, replication lag có ý nghĩa bảo mật.

### 27.1. Hợp đồng an toàn hơn

Đối với hành động nhạy cảm, hệ có thể:

- Kiểm tra quyền tại authority;
- Dùng revocation epoch/version;
- Gắn token/session với mốc quyền và kiểm tra mốc mới;
- Giới hạn thời gian sống của cached credentials;
- Từ chối hoặc đợi khi chưa xác nhận được quyền.

Cần xác định threat model và SLA của revoke. **Eventual consistency thường không phải hợp đồng đầy đủ cho quyền truy cập yêu cầu thu hồi tức thì.**

### 27.2. Bảo đảm per-session không thay authorization

Client có thể có token giúp RYW, nhưng token đó không cho phép đọc dữ liệu ngoài tenant hoặc bỏ qua quy tắc ACL. Consistency và security là những điều kiện độc lập cần cùng được thỏa.

## 28. Mẫu lựa chọn theo đường truy cập

| Yêu cầu | Phạm vi thật | Hướng thiết kế |
|---|---|---|
| Atomic increment view count | Một key | Atomic increment |
| Không oversell một SKU | Một item inventory | Conditional update/CAS |
| Không trùng username | Một business key toàn cục | Unique claim/constraint ở authority thích hợp |
| Cập nhật Order và Reservation cùng lúc | Nhiều item | Transaction theo scope hoặc workflow bền vững |
| Đọc báo cáo nhiều item tại cùng mốc | Tập nhiều bản ghi | Snapshot/serializable read hoặc data cut |
| Vừa lưu profile rồi reload đúng | Một phiên | RYW/session token hoặc strong route |
| Phone và laptop luôn thấy cùng trạng thái mới nhất | Nhiều session | Cross-session visibility contract/strong read |
| Đọc tài liệu ở region xa | Liên vùng | Chọn regional consistency/freshness SLA |
| Search kết quả mới trong vài giây | Projection | CDC lag/refresh SLO + reconciliation |
| Thu hồi ACL ngay | Nhiều service/session/region | Authoritative validation, revocation generation |
| Xuất toàn bộ dữ liệu không trùng/bỏ | Nhiều page | Snapshot/export/checkpoint, không chỉ offset |
| Thực hiện thanh toán không lặp | Nhiều hệ | Idempotency + ledger/reconciliation |

Lựa chọn đúng phải bắt đầu bằng **phạm vi của invariant và người quan sát**, không bắt đầu từ một tên consistency mode.

## 29. Đánh đổi hiệu năng theo phạm vi

### 29.1. Coordination càng rộng, chi phí có thể càng lớn

Với bảo đảm cần phối hợp nhiều máy hoặc nhiều region:

- Thêm network round trips;
- Thêm quorum/consensus work;
- Thêm contention;
- Tăng tail latency;
- Giảm khả năng chấp nhận write khi mất mạng;
- Tăng chi phí transaction/retry.

Một strong per-key operation trong cùng partition có thể rẻ hơn transaction atomic qua nhiều shard.

### 29.2. Nhưng weak consistency cũng có chi phí

Nếu chọn eventual consistency để tăng availability, ứng dụng có thể phải gánh:

- Conflict resolution;
- Idempotency;
- Reconciliation;
- UX đồng bộ trạng thái;
- Versioned read models;
- Giải quyết duplicate work;
- Support khi người dùng thấy dữ liệu khác nhau.

Chi phí không biến mất mà **dịch từ database coordination sang application correctness**.

### 29.3. Đừng nâng toàn bộ hệ lên mức mạnh nhất theo cảm tính

Một sản phẩm có thể cần:

- Strong/conditional operations cho inventory và quota;
- Serializable transactions cho transfer;
- Session consistency cho profile UI;
- Eventual replication cho analytics/search;
- Cross-region strong coordination cho một số quyền quản trị quan trọng.

Phân loại theo use case có thể cân bằng hiệu năng và tính đúng tốt hơn một cấu hình duy nhất cho mọi dữ liệu.

## 30. Thiết kế hợp đồng API có thể kiểm chứng

Một API cần nêu rõ:

1. Dữ liệu nào là nguồn authoritative?
2. Sau write thành công, client nhận bảo đảm gì?
3. Một read nào được coi là cùng session?
4. Read từ cache/index có thể stale bao lâu?
5. Dữ liệu từ region khác có phải đợi replication?
6. Transaction bảo vệ những object nào?
7. Khi không đáp ứng consistency yêu cầu, server đợi, trả lỗi hay trả stale cùng metadata?
8. Token/checkpoint có hiệu lực với partition/query/region nào?
9. Có hỗ trợ đọc tại một snapshot chung không?
10. Khi failover, dữ liệu đã ACK có bảo đảm còn lại không?

### 30.1. Mẫu hợp đồng “một phiên”

> Sau khi cập nhật profile thành công, các GET profile tiếp theo trong cùng session logic và cùng đường API sẽ không trả phiên bản cũ hơn phiên bản đã được xác nhận, miễn session token được duy trì theo hợp đồng.

### 30.2. Mẫu hợp đồng “projection eventual”

> Sau khi order commit ở source, danh sách tìm kiếm có thể chưa chứa order trong một khoảng trễ. API trả `sourceVersion` và trạng thái đồng bộ; những hành động cần trạng thái chính xác được kiểm tra lại ở source.

### 30.3. Mẫu hợp đồng “transaction”

> Các write thuộc transaction T trong nhóm tài nguyên được hỗ trợ sẽ được commit nguyên tử với isolation theo mức được chỉ định. Những read ở read model bên ngoài không được bao phủ.

### 30.4. Khi không thể thực hiện lời hứa

Nếu một replica chưa bắt kịp token hoặc vùng authority bị cô lập, backend không nên âm thầm giảm thành eventual read mà vẫn quảng cáo “đã thấy ghi của bạn”. Tùy nghiệp vụ, có thể:

- Đợi trong deadline;
- Route về nơi đủ mới;
- Trả lỗi retryable;
- Trả stale với nhãn/phiên bản rõ ràng **chỉ khi hợp đồng cho phép**.

## 31. Thiết kế kiểm thử consistency theo history

Kiểm thử đơn lẻ kiểu “PUT rồi GET” khi hệ khỏe rất dễ bỏ qua lỗi.

### 31.1. Thu thập operation history

Lưu:

~~~json
{
  "operationId": "op-1001",
  "clientId": "C1",
  "sessionId": "S1",
  "region": "A",
  "type": "WRITE",
  "key": "K1",
  "value": "v2",
  "startedAt": "...",
  "completedAt": "...",
  "result": "ACK"
}
~~~

Cần cả thời điểm start/end và kết quả. Khi timeout, ghi `UNKNOWN` thay vì tự đoán FAIL.

### 31.2. Test per-key linearizability

Cho nhiều client đọc/ghi cùng K, có thời gian chồng lấn. Phân tích liệu có một thứ tự hợp lệ tôn trọng real-time order của operation hoàn tất không.

Một kết quả stale sau một write đã hoàn tất, trong khi không có concurrent write liên quan, có thể vi phạm hợp đồng linearizable trên đường đọc đó.

### 31.3. Test transaction atomicity

Cố tình crash sau bước debit trước credit trong một workflow:

- Nếu dùng transaction, kiểm tra không có trạng thái commit nửa chừng.
- Nếu dùng saga/ledger, kiểm tra recovery/compensation đúng theo mô hình nghiệp vụ, không gọi nó là atomic transaction nếu không có bảo đảm đó.

### 31.4. Test session guarantees

Cho cùng session:

~~~text
WRITE K=v2
READ K
READ K
Switch region/replica
READ K
~~~

Kiểm tra read-your-writes và monotonic reads. Test phải giữ session token thực sự; nếu bỏ token thì đang test một đường khác.

### 31.5. Test causal ordering

Client A đăng P, client B đọc P rồi bình luận C. Quan sát liệu một client khác có thể thấy C trước P trong phạm vi mà hệ hứa causal order không.

### 31.6. Test cross-region lag

Ghi v2 ở A, đo thời gian B thấy v2, theo số lượng key và mức tải khác nhau. Đo p95/p99 và lúc failover, không chỉ trung bình.

Nếu sản phẩm không cam kết bounded staleness, đây là **observed lag**, không phải một giới hạn bảo đảm có thể tuyên bố tuyệt đối.

### 31.7. Test bằng lỗi phân tán

- Tắt/mất kết nối một replica;
- Tăng network delay;
- Network partition hai region;
- Failover leader;
- Clock skew theo test an toàn;
- Retry sau timeout/unknown commit;
- Consumer lag/CDC interruption;
- Phục hồi từ backup cũ.

Mọi thí nghiệm gây lỗi cần môi trường kiểm soát và kế hoạch phục hồi, không chạy tùy ý trên production.

## 32. Theo dõi consistency và freshness

| Nhóm metric | Ví dụ | Câu hỏi |
|---|---|---|
| Replication | Region/replica lag theo byte, thời gian, log position | Region B chậm bao xa? |
| Session | Số read phải đợi token, số lỗi không đáp ứng mốc | Có giữ RYW/MR không? |
| Transaction | Commit/abort/conflict/timeout | Invariant đa bản ghi có bị tranh chấp không? |
| Quorum | Đọc/ghi CL, timeout, unavailable | Có vùng/replica nào thiếu phản hồi? |
| Read model | SourceVersion - projectionVersion | Search/index/cache chậm đến đâu? |
| Failover | RPO quan sát, recovery time, rollback | ACK writes có được bảo vệ như đã hứa? |
| Correctness | Oversell, duplicate claim, fractured report, stale ACL | Có vi phạm nghiệp vụ không? |
| Latency | p50/p95/p99 theo consistency mode/region | Mức mạnh có ảnh hưởng UX? |
| Retry | Unknown outcome, duplicate request IDs | Có xử lý commit không rõ không? |
| Repair | Anti-entropy progress, tombstone risk | Replica có hội tụ an toàn không? |

Một hệ có p99 latency tốt nhưng đọc sai quyền hoặc làm mất đơn đã xác nhận vẫn không đạt tính đúng. Ngược lại, một hệ có consistency mạnh nhưng downtime vượt SLO cũng chưa chắc đáp ứng sản phẩm.

## 33. Các sai lầm thường gặp

**“Database hỗ trợ strong consistency nên mọi bảng, mọi region, mọi index đều strong.”** Sai. Phải xác định operation và scope.

**“Một document update nguyên tử nghĩa là toàn collection được cập nhật nguyên tử.”** Sai. Atomicity có ranh giới.

**“Các item chung partition key tự tạo transaction.”** Không. Cần tính năng transaction được hỗ trợ rõ.

**“Quorum read/write tự biến hai khóa thành ACID.”** Không. Quorum không gộp những mutation rời thành transaction.

**“Strong read là snapshot cho tất cả trang pagination.”** Không. Các trang cách nhau thời gian vẫn có thể quan sát tập dữ liệu thay đổi.

**“Snapshot isolation luôn ngăn write skew.”** Không. Cần xét invariant đa bản ghi.

**“Majority write có nghĩa secondary read luôn trả giá trị mới nhất.”** Không suy được nếu đường đọc/concern không tương ứng.

**“Session consistency là mọi người dùng đều thấy ghi mới.”** Không. Bảo đảm chủ yếu theo phiên/causal context được nhận diện.

**“Cùng userId thì hai thiết bị cùng database session.”** Không mặc định.

**“Bỏ session token vẫn có read-your-writes.”** Không thể giả định khi SDK phụ thuộc token.

**“Eventual consistency nghĩa sau đúng 1 giây mọi nơi đã đồng bộ.”** Không nếu không có bound chính thức.

**“Multi-region nghĩa write được ACK ở A đã tồn tại bền vững ở B.”** Không mặc định với async replication.

**“Last-writer-wins bảo vệ quota/uniqueness.”** Không. LWW có thể hợp nhất sai nghiệp vụ.

**“Transaction ở source tự làm search index hiện kết quả.”** Không. Projection có freshness riêng.

**“Bật strong consistency cho DB là cache cũng strong.”** Không. Cache phải có protocol riêng.

**“Kết quả GSI/search chưa có record nghĩa record chưa được ghi.”** Không. Có thể index lag.

**“Timeout của write nghĩa chắc chắn rollback.”** Không. Có thể commit đã xảy ra nhưng ACK bị mất.

**“Đọc được v2 một lần thì những lần sau luôn ít nhất v2.”** Chỉ khi đường đọc/session đáp ứng monotonic reads hoặc bảo đảm mạnh hơn.

**“Causal consistency và atomic multi-key transaction giống nhau.”** Không. Causal order không làm nhiều mutation thành một commit.

**“Toàn bộ NoSQL chỉ có eventual consistency.”** Không đúng. Các hệ cung cấp nhiều mức và API với phạm vi khác nhau.

## 34. Quy trình ra quyết định từ yêu cầu nghiệp vụ

### Bước 1 — Viết điều không được phép xảy ra

Ví dụ:

- Tồn kho không âm;
- Một email chỉ thuộc một user;
- Một transfer không mất một vế;
- Người dùng vừa lưu không nhìn trạng thái cũ;
- Quyền bị thu hồi không còn được dùng để thao tác;
- Một báo cáo có snapshot chung.

### Bước 2 — Khoanh vùng dữ liệu của invariant

- Một key?
- Một partition?
- Nhiều item?
- Nhiều read model?
- Nhiều region?
- Một session hay mọi session?

Nếu không xác định ranh giới, không thể chọn đúng bảo đảm.

### Bước 3 — Xác định đường đọc/ghi

- Đọc leader hay replica?
- Query index phụ hay bảng nguồn?
- Cache có tham gia không?
- API có session token không?
- Client có thể đổi region không?
- Write có được ACK trước khi replicate toàn cục không?

### Bước 4 — Chọn operation/transaction native

Ưu tiên cơ chế do database thực thi:

- Atomic increment/conditional write cho một key;
- Transaction cho nhiều item trong phạm vi hỗ trợ;
- Session token/casual read trong đường đọc tương ứng;
- Cross-region coordination nếu cần global invariant;
- Snapshot/export khi cần tập dữ liệu cố định.

Không tự mô phỏng strong consistency bằng check-then-write ngoài DB.

### Bước 5 — Định nghĩa staleness chấp nhận được

Một số dữ liệu có thể trễ:

- Analytics dashboard vài phút;
- Search vài giây;
- Profile trong cùng session gần như ngay sau write theo hợp đồng;
- Tồn kho tại thời điểm reserve không được kiểm tra trên cache stale;
- ACL có thể cần authoritative check.

Phải nêu rõ cái nào là **hard guarantee**, cái nào chỉ là **operational SLO**.

### Bước 6 — Xử lý lỗi và retry

Định nghĩa:

- Conflict;
- Timeout/unknown commit;
- Replica unavailable;
- Region failover;
- Session token không thể đáp ứng;
- Projection lag;
- Partial workflow failure.

Kèm idempotency, retry/backoff và reconciliation thích hợp.

### Bước 7 — Kiểm thử đúng phạm vi

Test phải gồm concurrency và failover trên đường thực tế, không chỉ một request trên một node khỏe.

## 35. Bài tập thực hành

### Bài tập 1 — Một khóa không phải hai khóa

Inventory và Order nằm ở hai item. Inventory conditional decrement thành công, tạo Order thất bại.

**Câu hỏi:** Per-item atomicity đã đủ để bảo đảm cả hai bước commit chưa?

**Gợi ý:** Chưa. Cần transaction nhiều item trong phạm vi hỗ trợ hoặc reservation/workflow bền vững.

### Bài tập 2 — RYW theo session

Client A ghi profile v7, sau đó chính A đọc replica khác ra v6.

**Câu hỏi:** Bảo đảm nào bị vi phạm nếu API đã hứa client luôn thấy ghi mới của mình?

**Gợi ý:** Read-your-writes; cần token/route phù hợp.

### Bài tập 3 — Monotonic reads

Một client đọc version 9 ở region A, sau đó đọc version 7 ở B.

**Câu hỏi:** Điều đó có thể hợp lệ theo eventual consistency không? Có hợp lệ với monotonic reads trong cùng session không?

**Gợi ý:** Có thể xảy ra với eventual; vi phạm MR nếu không có ghi mới đảo ngữ nghĩa và hợp đồng session còn hiệu lực.

### Bài tập 4 — Hai thiết bị

Phone lưu ngôn ngữ "en" và thấy "en". Laptop cùng tài khoản vẫn thấy "vi" vài giây.

**Câu hỏi:** Có mâu thuẫn với read-your-writes của phone không?

**Gợi ý:** Không nhất thiết. Hai thiết bị không mặc định cùng phiên; cần hợp đồng cross-session/cross-region riêng.

### Bài tập 5 — Quorum intersection

RF=3, R=2, W=2.

**Câu hỏi:** Vì sao hai tập replica phải giao nhau? Có đủ để kết luận mọi transaction nhiều khóa là serializable không?

**Gợi ý:** R+W>RF làm tập giao nhau trong mô hình đơn giản; không suy ra multi-key serializability.

### Bài tập 6 — DynamoDB GSI

Ứng dụng update item status=PAID thành công, query GSI theo status không thấy item.

**Câu hỏi:** Có chắc update thất bại?

**Gợi ý:** Không. GSI cập nhật bất đồng bộ, nên đường query index có thể chậm so với bảng cơ sở.

### Bài tập 7 — Cassandra LOCAL_QUORUM

Client ghi vào DC A với LOCAL_QUORUM, rồi chuyển DC B và đọc theo consistency cục bộ.

**Câu hỏi:** Có tự bảo đảm B luôn thấy bản mới ngay không?

**Gợi ý:** Không. Cần xem replication, data center scope và đường read thực tế.

### Bài tập 8 — Snapshot isolation và write skew

Hai transaction tắt cờ onCall của hai bác sĩ khác nhau, mỗi transaction đọc snapshot thấy người kia đang trực.

**Câu hỏi:** Vì sao vẫn có thể kết thúc không còn ai trực?

**Gợi ý:** Hai transaction ghi các record khác nhau; snapshot isolation không nhất thiết chặn write skew.

### Bài tập 9 — Cosmos session token

Backend nhận POST rồi GET ở hai pod khác nhau, pod sau không có token của session trước.

**Câu hỏi:** Vấn đề thiết kế là gì?

**Gợi ý:** Phiên logic không được duy trì qua request; cần token propagation hoặc strong route phù hợp.

### Bài tập 10 — Multi-region asynchronous

Region A xác nhận v2, B còn v1.

**Câu hỏi:** “Write durable tại A” có đồng nghĩa “read ở B đã thấy v2” không?

**Gợi ý:** Không. Durability phạm vi A và visibility tại B là hai điều khác nhau.

### Bài tập 11 — Ghi xung đột đa vùng

A và B cùng chấp nhận tạo username `an.nguyen` trước khi replicate, sau đó LWW chỉ giữ một record.

**Câu hỏi:** Có thỏa hợp đồng “chỉ một người được xác nhận đăng ký thành công” không?

**Gợi ý:** Không. Cần authority/coordination để ngăn hai xác nhận xung đột, không chỉ giải quyết sau.

### Bài tập 12 — Search refresh

Source commit document, nhưng `_search` không thấy trong 200 ms.

**Câu hỏi:** Có thể kết luận source không lưu dữ liệu?

**Gợi ý:** Không. Search refresh/replication có đường visibility khác source.

### Bài tập 13 — Báo cáo hai số dư

Một report đọc A trước, B sau trong lúc đang chuyển tiền, tổng sai tạm thời.

**Câu hỏi:** Chọn strong read riêng từng key đã đủ chưa?

**Gợi ý:** Chưa nếu cần cùng snapshot; dùng transaction/snapshot/data cut thích hợp.

### Bài tập 14 — Cache và quyền

Admin revoke quyền, nguồn đã commit, cache ACL còn giá trị cũ.

**Câu hỏi:** Nên xử lý ở đâu nếu thao tác cần thu hồi tức thì?

**Gợi ý:** Authority/revocation epoch và cache invalidation/bypass phù hợp; session guarantee của user không đủ.

### Bài tập 15 — Unknown commit

PUT v2 timeout nhưng server đã commit. Client retry vô điều kiện cùng business action có side effect.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Có thể nhân đôi business action. Cần idempotency và reconcile thay vì xem timeout là rollback.

### Bài tập 16 — Phân trang snapshot

Trang 1 được đọc với strong consistency, sau đó thêm record mới, trang 2 dùng offset.

**Câu hỏi:** Có chắc kết quả hai trang là một snapshot cố định không?

**Gợi ý:** Không. Strong read từng trang không tự có snapshot xuyên các lần gọi.

### Bài tập 17 — Causal order

B đọc bài P rồi viết comment C. Một client thấy C nhưng chưa có P.

**Câu hỏi:** Cần phân tích bảo đảm gì?

**Gợi ý:** Quan hệ nhân quả P→C và phạm vi causal consistency của đường đọc/projection.

### Bài tập 18 — Chọn consistency đúng chỗ

Hệ có bốn nhu cầu:

1. Không oversell inventory;
2. UI thấy profile mới của chính mình;
3. Analytics cập nhật mỗi phút;
4. Chuyển tiền giữa hai tài khoản.

**Gợi ý:** (1) conditional item update; (2) RYW/session; (3) eventual với freshness SLO; (4) transaction/ledger giữ invariant đa bản ghi.

### Bài tập 19 — Tính cost

Một write cần ACK từ region A và B, RTT giữa hai vùng lớn. Team muốn giảm p99 bằng cách chỉ ACK A rồi replicate B sau.

**Câu hỏi:** Đổi này có thể ảnh hưởng những bảo đảm nào?

**Gợi ý:** Cross-region visibility/durability, failover RPO, latency và availability; phải thay hợp đồng và kiến trúc recovery.

### Bài tập 20 — Thiết kế API

Hãy viết hợp đồng cho API chỉnh sửa hồ sơ với:

- Version/ETag cho optimistic concurrency;
- RYW trong cùng phiên;
- TTL của token theo policy;
- Đường đọc khi region hiện tại chưa bắt kịp;
- Conflict response;
- Không hứa search index cập nhật tức thì.

**Gợi ý:** Nêu rõ request/response, session token, scope của guarantee và đường xử lý khi không thể đáp ứng mốc.

## 36. Checklist kiểm tra phạm vi bảo đảm

- [ ] Có danh sách invariant quan trọng theo nghiệp vụ.
- [ ] Đã xác định per-key atomicity cần thiết.
- [ ] Đã phân biệt logical partition với item và physical shard.
- [ ] Không giả định cùng partition tự có multi-item transaction.
- [ ] Đã nêu transaction boundary và isolation level.
- [ ] Đã kiểm tra snapshot isolation có đủ hay cần serializability.
- [ ] Đã xác định read/write concerns và read preferences cụ thể.
- [ ] Đã định nghĩa session và cách truyền token.
- [ ] Đã kiểm tra read-your-writes và monotonic reads nếu UI yêu cầu.
- [ ] Đã xác định region nhận write/ACK và region phục vụ read.
- [ ] Đã đánh giá multi-region conflict và failover.
- [ ] Đã phân biệt consistency read với durability/RPO.
- [ ] Đã ghi rõ GSI/search/cache/read model có thể stale.
- [ ] Đã chọn authoritative path cho quyết định tiền, tồn kho và quyền.
- [ ] Đã xác định bounded staleness thật hay chỉ freshness SLO quan sát.
- [ ] Đã thiết kế xử lý timeout/unknown commit/idempotency.
- [ ] Có test concurrency, region switching, partition/failover và read model lag.
- [ ] Có monitoring replication lag, conflict, transaction abort và correctness.
- [ ] API không tuyên bố strong/session guarantee trên đường đọc không hỗ trợ.
- [ ] Các cam kết được đối chiếu với phiên bản/configuration sản phẩm dùng thực tế.

## 37. Tổng kết

**Phạm vi của bảo đảm nhất quán là một phần của chính bảo đảm đó.** Một cập nhật nguyên tử trên khóa K không tự bảo vệ hai khóa K1 và K2. Một thứ tự nhất quán trong partition không tự tạo transaction xuyên partition. Một transaction đa bản ghi không tự khiến cache/search/analytics cập nhật đồng thời. Một phiên có read-your-writes không buộc mọi session hay region khác nhìn thấy ghi mới ngay.

Khi làm việc với NoSQL, hãy tách rõ:

1. **Mức nhất quán:** linearizable, causal, session, eventual, bounded staleness, snapshot/serializable...
2. **Phạm vi:** key/document, partition, transaction, session, region, nhiều region và read model.
3. **Đường thao tác:** GET nguồn, query index phụ, cache, transaction, message/CDC.
4. **Mô hình lỗi:** crash, replica lag, leader failover, partition mạng, timeout/unknown commit.

Các hệ như DynamoDB, Cassandra, MongoDB, Cosmos DB, Firestore, Redis và search engines đưa ra các cơ chế khác nhau. Không thể chọn chỉ bằng nhãn “NoSQL” hay một setting “strong”; cần đối chiếu **bất biến nghiệp vụ, ranh giới dữ liệu, consistency configuration, đường đọc thực tế và chi phí phối hợp**.

**Nguyên tắc quan trọng nhất:** chỉ hứa một kết quả quan sát hoặc một bất biến khi toàn bộ thao tác liên quan nằm trong phạm vi mà hệ thực sự bảo đảm. Nếu invariant vượt ranh giới đó, hãy dùng transaction/authority phù hợp hoặc thiết kế một workflow có version, idempotency, retry và reconciliation rõ ràng — thay vì mở rộng một bảo đảm cục bộ bằng suy đoán.

