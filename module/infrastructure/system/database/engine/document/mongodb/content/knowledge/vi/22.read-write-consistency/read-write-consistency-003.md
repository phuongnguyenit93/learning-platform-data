# Read concern: local, available, majority, linearizable và snapshot trong MongoDB

## 1. Vì sao một lần đọc MongoDB có thể thấy dữ liệu khác nhau?

Trong ứng dụng sử dụng MongoDB replica set, một document có thể đang nằm ở các trạng thái khác nhau tại cùng một thời điểm:

- **Primary** đã nhận một lần ghi mới.
- Một **secondary** đã nhận bản sao của lần ghi đó.
- Một secondary khác vẫn chưa đồng bộ kịp.
- Lần ghi mới có thể chưa được đa số thành viên replica set xác nhận.
- Sau sự cố bầu primary, một số lần ghi chưa được majority commit có thể bị **rollback**.

Ví dụ một đơn hàng:

~~~javascript
{
  _id: "ORD-100",
  tenantId: "SHOP-A",
  status: "PENDING",
  totalCents: NumberLong(350000)
}
~~~

Ứng dụng cập nhật:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
);
~~~

Ngay sau thao tác, client A đọc trên primary có thể thấy **PAID**, còn client B đọc từ secondary đang lag có thể thấy **PENDING**. Nếu lần ghi chưa đạt majority commit và primary bị thay đổi trong tình huống lỗi thích hợp, phiên bản **PAID** mà client đã đọc với mức yếu có thể không tồn tại sau rollback.

**Read concern** là cơ chế quy định **những bảo đảm nhất quán và cô lập của dữ liệu mà một thao tác đọc được phép trả về**. Nó không tự chọn server để đọc, cũng không quyết định lúc nào write được xác nhận.

MongoDB có năm mức read concern trọng tâm:

1. **local**
2. **available**
3. **majority**
4. **linearizable**
5. **snapshot**

Chọn đúng read concern nghĩa là cân bằng **consistency**, **freshness**, **availability**, **latency** và **chi phí vận hành** theo yêu cầu thực tế của từng API.

### Mục tiêu bài học

Sau bài này, bạn cần:

- Giải thích mỗi read concern bảo đảm điều gì và **không** bảo đảm điều gì.
- Phân biệt read concern với **read preference** và **write concern**.
- Dự đoán kết quả khi primary, secondary và majority commit point chưa đồng bộ.
- Dùng read concern trong mongosh, Java Sync Driver và Spring Data MongoDB.
- Chọn **majority**, **linearizable** hoặc **snapshot** cho từng yêu cầu nghiệp vụ.
- Hiểu giới hạn của đọc trên sharded cluster, trong transaction và causal session.
- Thiết kế timeout, retry, kiểm thử failover và giám sát consistency.

## 2. Ba cấu hình dễ nhầm: read preference, read concern, write concern

Một thao tác MongoDB có thể chịu ảnh hưởng của cả ba lựa chọn độc lập:

| Cấu hình | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **Read preference** | Đọc **từ node nào**? | primary, secondary, secondaryPreferred, nearest. |
| **Read concern** | Dữ liệu đọc phải đạt **mức nhất quán/cô lập nào**? | local, majority, snapshot. |
| **Write concern** | Khi nào một thao tác ghi được **xác nhận**? | w:1, w:"majority", journal. |

Ví dụ:

~~~text
Write:
  Client -- update --> Primary
                      |
                      +--> Secondary A
                      +--> Secondary B

Write concern:
  Chờ bao nhiêu thành viên xác nhận?

Read preference:
  Đọc primary hay secondary?

Read concern:
  Phiên bản dữ liệu nào được phép trả về?
~~~

Nếu đặt **readPreference: secondary**, driver ưu tiên đọc secondary. Nếu kết hợp với **readConcern: majority**, dữ liệu trả về phải thuộc phần majority-committed mà secondary đã có thể phục vụ, **nhưng vẫn có thể cũ** so với primary.

Nếu dùng **writeConcern: majority** cho ghi, điều đó **không tự thay read concern của mọi truy vấn sau**. Ngược lại, chỉ đặt readConcern majority không buộc mọi ứng dụng khác ghi với w:majority.

**Không có một nút cấu hình “strong consistency” duy nhất tự giải quyết mọi khía cạnh.**

## 3. Sơ đồ replica set và majority commit point

Giả sử replica set ba data-bearing nodes:

~~~text
                  MongoDB Replica Set

                     PRIMARY (P)
                         |
               +---------+---------+
               |                   |
               v                   v
         SECONDARY (S1)       SECONDARY (S2)

        Majority = 2 trong 3 thành viên
~~~

Timeline minh họa một write **W1**:

| Thời điểm | P | S1 | S2 | Trạng thái W1 |
|---|---|---|---|---|
| t0 | Đã áp dụng W1 | Chưa áp dụng | Chưa áp dụng | Chưa majority committed. |
| t1 | Đã áp dụng W1 | Đã áp dụng W1 | Chưa áp dụng | Đã có ở hai node; primary có thể xác nhận majority sau khi nắm được tiến độ replication theo cơ chế tương ứng. |
| t2 | Biết W1 đạt majority commit point | Đã áp dụng W1 | Chưa áp dụng | Dữ liệu W1 đủ điều kiện thuộc phần majority committed. |
| t3 | Đã áp dụng W1 | Đã áp dụng W1 | Đã áp dụng W1 | Toàn bộ các node trong ví dụ đã có W1. |

Đây là **mô hình minh họa**, không phải cam kết về độ trễ replication hay thứ tự phát thông báo commit của MongoDB.

Các khái niệm:

- **Applied write:** node đã áp dụng thay đổi vào dữ liệu cục bộ.
- **Majority-acknowledged write:** thao tác ghi đã được xác nhận theo write concern **w:"majority"**.
- **Majority commit point:** ranh giới mà replica set xác định các thao tác đủ điều kiện majority committed.
- **Replication lag:** secondary chậm hơn primary trong quá trình áp dụng/nhận biết tiến độ ghi.
- **Rollback:** thao tác chưa được majority commit có thể bị loại khỏi lịch sử khi replica set khôi phục sau sự cố.

Đừng đồng nhất “secondary đã áp dụng W1” với “mọi read concern ở secondary đều có thể trả W1 ngay lập tức”. Với **majority** còn có ranh giới majority commit view mà node sử dụng.

## 4. Bảng so sánh nhanh năm mức read concern

| Mức | Bảo đảm chính | Có thể stale? | Có thể đọc dữ liệu rollback? | Hạn chế/chú ý |
|---|---|---|---|---|
| **local** | Đọc dữ liệu khả dụng cục bộ trên node được chọn, không đòi majority commit. | Có, đặc biệt trên secondary. | **Có.** | Mặc định phổ biến khi không có override. |
| **available** | Tập trung khả dụng, giảm yêu cầu kiểm tra phân vùng/shard ownership ở sharded cluster. | Có. | **Có.** | Sharded collection có thể trả **orphaned documents** hoặc kết quả sai kỳ vọng do routing trong partition; không dùng trong transaction/causal session. |
| **majority** | Chỉ trả dữ liệu đã được majority commit của replica set. | **Có.** | Theo bảo đảm majority commit, không rollback trong các điều kiện durability mặc định. | Không tự bảo đảm đọc đúng bản ghi mới nhất theo real-time. |
| **linearizable** | Phản ánh các majority-acknowledged writes hoàn tất trước lúc bắt đầu đọc; tính thứ tự real-time khi kết hợp write concern majority đúng cách. | Không đối với các writes đã hoàn tất thuộc bảo đảm đó; đọc vẫn có thể chờ hoặc timeout. | Mục tiêu là mạnh hơn majority về recency/real-time. | **Chỉ đọc primary, truy vấn định danh duy nhất một document**, không trong transaction/causal session; cần maxTimeMS. |
| **snapshot** | Góc nhìn dữ liệu **ở một thời điểm nhất quán**, có thể xuyên shards. | Có, vì snapshot có thể ở quá khứ. | Ngoài transaction dùng majority-committed snapshot; trong transaction bảo đảm liên quan commit majority. | Transaction hoặc các đọc ngoài transaction được hỗ trợ từ MongoDB 5.0; giới hạn snapshot history. |

Đây không phải bảng xếp hạng “mức sau luôn tốt hơn mức trước”. **linearizable** và **snapshot** giải quyết **hai câu hỏi khác nhau**:

- **linearizable:** “Nếu một ghi majority đã hoàn tất trước khi đọc bắt đầu, lần đọc đơn-document này có thấy trạng thái phù hợp không?”
- **snapshot:** “Những dữ liệu tôi đọc có cùng thuộc một thời điểm nhất quán không, kể cả across shards?”

Một snapshot lịch sử có thể nhất quán hoàn hảo tại thời điểm T nhưng **cũ hơn dữ liệu hiện tại**. Ngược lại một lần đọc linearizable đơn-document không tự biến cả một báo cáo nhiều collection thành snapshot nhất quán.

## 5. Read concern "local"

### 5.1. Ý nghĩa

**local** trả dữ liệu từ node được chọn mà **không yêu cầu nó đã được đa số thành viên replica set xác nhận**.

Đây là mức read concern mặc định thông dụng cho các reads trên primary và secondary, nếu deployment không cấu hình default khác.

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
).readConcern("local");
~~~

Tương đương ví dụ dùng database command:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "ORD-100" },
  readConcern: { level: "local" }
});
~~~

### 5.2. local trên primary

Nếu primary đã áp dụng W1 nhưng chưa majority committed, đọc local từ primary **có thể thấy W1**.

~~~text
P: W0 -> W1 đã áp dụng
S1: W0
S2: W0

readPreference primary
readConcern local
       |
       v
Có thể trả W1
~~~

Vì W1 chưa majority committed, nếu xảy ra failover theo điều kiện phù hợp, W1 **có thể rollback**.

### 5.3. local trên secondary

Nếu read preference là secondary, local đọc bản dữ liệu cục bộ của secondary đó. Nếu replication lag, read có thể **stale**:

~~~text
P: W1
S1: W1
S2: W0  <-- secondary đang lag

Read local tại S2 -> có thể thấy W0
~~~

**local không có nghĩa đọc mới nhất của toàn cluster.** Nó có nghĩa đọc theo trạng thái node đang phục vụ và không đòi majority commit.

### 5.4. Khi nào dùng local?

Phù hợp khi:

- Ứng dụng chấp nhận khả năng đọc dữ liệu chưa majority committed.
- Các báo cáo/hiển thị có thể xử lý tình trạng stale hoặc rollback.
- Mục tiêu giảm overhead nhất quán đối với một số truy vấn thông thường.
- Đã có biện pháp kiểm soát invariant quan trọng ở write path.

Không nên chỉ dựa vào local read để quyết định một nghiệp vụ đòi hỏi dữ liệu majority durable hoặc real-time ordering, ví dụ “đã xác nhận quyền tài nguyên được cấp trên primary hiện hành hay chưa”.

### 5.5. local trong transaction

Transactions hỗ trợ read concern local, nhưng ngữ cảnh khác với một lệnh đọc riêng lẻ. Trên replica set, transaction local có thể quan sát một góc nhìn được cố định khi transaction bắt đầu. Trên sharded cluster, **local không bảo đảm mọi shard dùng cùng một snapshot**; nếu cần cross-shard snapshot isolation, nên chọn **snapshot**.

## 6. Read concern "available"

### 6.1. Điểm giống với local

**available** cũng đọc dữ liệu của instance **không yêu cầu majority commit**. Document được trả về **có thể rollback**.

Với **unsharded collection** trong standalone hoặc replica set, available và local có hành vi tương đương theo tài liệu MongoDB.

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
).readConcern("available");
~~~

Không nên diễn giải rằng available **bảo đảm dữ liệu mới hơn local** hoặc **không bao giờ chờ bất kỳ hoạt động nào**. Khác biệt quan trọng xuất hiện trong **sharded cluster**.

### 6.2. Available ưu tiên khả dụng trong sharded cluster

Ở sharded cluster, dữ liệu được chia theo chunks trên nhiều shards. Khi chunk migration, vùng dữ liệu có thể đang được chuyển giữa shards và cần kiểm tra shard nào là **authoritative owner**.

Với read concern available, trong tình huống network partition, truy vấn có thể được route đến shard được coi là thích hợp dựa trên thông tin trước khi phân vùng mạng, **không chờ các kiểm tra consistency với server đang không khả dụng**.

~~~text
             mongos
               |
               v
     Metadata/shard routing
            /     \
           v       v
        Shard A   Shard B

Chunk đang migrate A -> B
Network partition xảy ra

ReadConcern available:
  Không chờ xác minh ownership tương ứng
  -> có thể đọc từ shard không còn là owner hợp lệ
  -> có thể trả orphaned document
~~~

**Orphaned document** là bản dữ liệu tồn tại vật lý trên shard nhưng không còn thuộc chunk mà shard đó sở hữu về mặt logic, thường xuất hiện liên quan quá trình migration/cleanup.

Kết quả có thể không như ứng dụng mong muốn: **document mồ côi**, dữ liệu không đúng owner hoặc kết quả sai kỳ vọng về tính duy nhất/toàn vẹn trong sharded query.

### 6.3. Khi nào cân nhắc available?

Một số truy vấn chấp nhận nhất quán yếu để ưu tiên phản hồi khi sharded cluster bị partition, ví dụ giám sát/tổng hợp dữ liệu có thể sai lệch tạm thời.

Không nên dùng available cho:

- Kiểm kê tồn kho đòi không lặp/không thiếu document.
- Điều kiện tính tiền, thanh toán và kiểm soát quyền truy cập.
- Báo cáo cần đúng ownership của sharded data.
- Các nghiệp vụ không chấp nhận orphaned records.

Nếu không có yêu cầu đặc biệt, **local** thường là lựa chọn ít rủi ro hơn khi cần đọc dữ liệu với mức yếu trên sharded collection.

### 6.4. Giới hạn sử dụng

Theo tài liệu, read concern available **không được dùng trong causally consistent sessions hoặc multi-document transactions**.

Nó không phải một kỹ thuật để khắc phục replication lag hay bảo đảm read-your-writes.

## 7. Read concern "majority"

### 7.1. Ý nghĩa

**majority** chỉ trả dữ liệu thuộc tập đã được **đa số thành viên replica set xác nhận/majority committed**. Khi đọc ngoài multi-document transaction, các document đọc được có bảo đảm durability và **không bị rollback theo cơ chế replica set thông thường**.

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
).readConcern("majority");
~~~

Hoặc:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "ORD-100" },
  readConcern: { level: "majority" }
});
~~~

### 7.2. Trường hợp local thấy W1 nhưng majority chưa thấy

~~~text
Thời điểm t0:

P:  W1 đã áp dụng
S1: W0
S2: W0

readConcern local tại P
  -> có thể thấy W1

readConcern majority tại P
  -> chỉ nhìn majority-committed view,
     có thể vẫn thấy W0
~~~

Sau khi W1 đạt majority commit point, các node cập nhật majority view theo replication mechanism. Một majority read trên một secondary chưa cập nhật majority view của W1 **vẫn có thể trả W0**.

### 7.3. majority không có nghĩa luôn freshest

Đây là sai lầm thường gặp:

> “Dùng read concern majority thì bất kỳ node nào cũng trả trạng thái mới nhất của primary.”

**Không đúng.** majority tập trung vào việc chỉ trả **dữ liệu đã majority committed**, không bảo đảm thao tác đọc phản ánh toàn bộ majority writes hoàn tất trước đó theo thứ tự real-time trong mọi tình huống.

Ví dụ một secondary đang lag có thể trả majority-committed snapshot cũ, trong khi một majority write khác đã được primary xác nhận.

Nếu yêu cầu là **đọc bản mới nhất với thứ tự real-time** cho một document được định danh duy nhất, cần xem **linearizable**. Nếu yêu cầu đọc theo chuỗi nhân quả của cùng một người dùng, cần xem **causally consistent session** với read/write concern phù hợp.

### 7.4. Majority read và majority write

Hai cấu hình độc lập:

~~~javascript
// Ghi với majority write concern.
db.runCommand({
  update: "orders",
  updates: [
    {
      q: { _id: "ORD-100" },
      u: { $set: { status: "PAID" } }
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 10000
  }
});

// Đọc majority.
db.orders.find(
  { _id: "ORD-100" }
).readConcern("majority");
~~~

**writeConcern majority** điều khiển lúc write được xác nhận. **readConcern majority** điều khiển dữ liệu có thể được đọc. Kết hợp đúng có ý nghĩa quan trọng, nhưng **không tự tạo một session nhân quả** giữa mọi request độc lập.

### 7.5. majority trong transaction

Trong multi-document transaction, **read concern majority chỉ cung cấp bảo đảm majority tương ứng khi transaction commit với write concern majority**.

Đừng mặc định transaction với readConcern majority nhưng commit bằng w:1 sẽ có bảo đảm giống majority committed transaction.

Nếu cần một snapshot nhất quán trên nhiều documents/shards trong transaction, dùng readConcern **snapshot** và commit với writeConcern **majority** theo yêu cầu của ứng dụng.

### 7.6. Lưu ý durability và cấu hình bất thường

MongoDB với cấu hình journaling mặc định phù hợp cung cấp bảo đảm majority durability. Một số cấu hình đặc biệt như **writeConcernMajorityJournalDefault:false** hoặc các trường hợp đa số node crash/restart cùng lúc có những caveats riêng.

Không nên diễn đạt “majority tuyệt đối không bao giờ mất dữ liệu trong mọi lỗi phần cứng/tùy chọn”. Cần kiểm tra journal, topology, write concern và cấu hình deployment.

### 7.7. Khi nào dùng majority?

Các ví dụ:

- Người dùng xem trạng thái giao dịch đã xác nhận majority nhưng không cần real-time linearizability cho từng read.
- API cần tránh hiển thị write dễ rollback.
- Hệ thống có session yêu cầu causal consistency khi kết hợp majority read/write.
- Báo cáo cần dữ liệu đã majority committed nhưng chấp nhận sự chậm trễ hợp lý.

**majority không thay thế business validation, transactions, OCC hoặc unique indexes.**

## 8. Read concern "linearizable"

### 8.1. Bảo đảm chính

**linearizable** nhằm bảo đảm thao tác đọc phản ánh **mọi majority-acknowledged writes đã hoàn tất trước khi read bắt đầu**.

Khi kết hợp với **write concern majority**, ứng dụng có thể coi các thao tác đọc/ghi trên **một document** như được thực hiện theo một thứ tự nhất quán với **thứ tự thời gian thực**.

~~~text
Write W1 với w:majority được xác nhận
                   |
                   v
             Read R1 bắt đầu
               linearizable
                   |
                   v
R1 phải quan sát trạng thái phù hợp sau W1
trong phạm vi bảo đảm single-document
~~~

Khác với majority, MongoDB còn phải xác nhận rằng node primary đang phục vụ có khả năng thực hiện những majority writes hợp lệ. Điều này quan trọng khi một node cũ chưa nhận ra đã mất vai trò primary trong network partition.

### 8.2. Chỉ đọc trên primary

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
)
.readConcern("linearizable")
.maxTimeMS(5000);
~~~

Ví dụ rõ ràng hơn qua command:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "ORD-100" },
  readConcern: { level: "linearizable" },
  maxTimeMS: 5000
});
~~~

Driver cần route thao tác **tới primary**. Không kết hợp linearizable với **readPreference: secondary**.

### 8.3. Chỉ bảo đảm với truy vấn định danh duy nhất một document

Bảo đảm linearizable của MongoDB **chỉ áp dụng** khi query filter định danh duy nhất một document. Một số điều kiện bổ sung về search key cũng cần được thỏa để có consistent snapshot:

- Dùng **field bất biến** làm search key, điển hình **_id**.
- Hoặc search key không bị cập nhật đồng thời.
- Hoặc query dùng một **unique index** thích hợp trên search key.

Ví dụ phù hợp:

~~~javascript
db.feature_flags.find(
  { _id: "checkout.enabled" }
)
.readConcern("linearizable")
.maxTimeMS(5000);
~~~

Không giả định một **find({status:"ACTIVE"})** trả hàng nghìn document có cùng bảo đảm linearizable toàn tập hoặc across collections.

### 8.4. Vì sao cần maxTimeMS?

Khi đa số data-bearing members không khả dụng, thao tác linearizable có thể chờ rất lâu để thỏa điều kiện. MongoDB khuyến nghị **luôn đặt maxTimeMS** để thao tác có thể trả lỗi timeout thay vì chặn không có giới hạn.

Nếu read timeout:

- Đừng tự coi kết quả là “không có document” hoặc “flag = false”.
- Phân loại đây là **không thể xác minh consistency trong timeout**, không phải một giá trị dữ liệu nghiệp vụ.
- Chọn fallback phù hợp với rủi ro của chức năng; với hoạt động nhạy cảm có thể phải fail closed.

### 8.5. Ví dụ cần linearizable

Một hệ thống điều phối job có document:

~~~javascript
{
  _id: "leader-controller",
  ownerId: "worker-A",
  epoch: NumberLong(18)
}
~~~

Nếu nhiều bên cần **đọc trạng thái leader đã được majority ghi trước đó theo real-time**, linearizable có thể phù hợp cho phép đọc chính xác một document.

Tuy nhiên, chỉ đọc linearizable không tự xây được một giao thức lease/leader election an toàn. Muốn thay owner, phải dùng **conditional write**, fencing token/epoch, write concern và xử lý timeout/network partition phù hợp.

### 8.6. Giới hạn sử dụng

- Chỉ đọc **primary**.
- Không dùng trong **causally consistent session** hoặc **multi-document transaction**.
- Với aggregation read concern linearizable, không dùng **$out** hoặc **$merge**.
- Bảo đảm gắn với **một document được query định danh duy nhất**, không phải snapshot cả báo cáo.
- Có thể chậm hơn **local/majority** đáng kể vì cần kiểm tra thêm.

### 8.7. Tránh lạm dụng

Không cần linearizable cho mọi danh sách sản phẩm, log hoặc bảng dashboard. Chọn nó cho những reads thật sự cần real-time ordering với majority writes và có thể chấp nhận thêm độ trễ/giảm availability.

## 9. Read concern "snapshot"

### 9.1. Mục tiêu: đọc tại một thời điểm nhất quán

**snapshot** cung cấp dữ liệu majority committed theo **một thời điểm logic nhất quán**; có thể là góc nhìn xuyên shards.

Giả sử hệ thống có hai documents:

~~~javascript
{
  _id: "ACCOUNT-A",
  balance: NumberLong(1000)
}

{
  _id: "ACCOUNT-B",
  balance: NumberLong(500)
}
~~~

Một transfer chuyển 200 từ A sang B. Nếu report đọc A trước và B sau vào những thời điểm không nhất quán, report có thể thấy các giá trị thuộc những thời điểm khác nhau.

**Snapshot read** hướng tới việc các phần dữ liệu trong phạm vi snapshot cùng phản ánh một **góc nhìn tại T**, thay vì document này thuộc trước thay đổi và document kia thuộc sau thay đổi mà không có ranh giới nhất quán.

**Quan trọng:** snapshot read không tự làm thao tác chuyển tiền nhiều document trở thành nguyên tử. Transfer vẫn cần transaction hoặc data model phù hợp nếu nghiệp vụ yêu cầu atomicity xuyên documents.

### 9.2. Snapshot trong transaction

Trong một multi-document transaction, có thể cấu hình:

~~~javascript
const session = db.getMongo().startSession();
const database = session.getDatabase("mongo_consistency_lab");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: { mode: "primary" }
  });

  const accountA = database.accounts.findOne(
    { _id: "ACCOUNT-A" }
  );
  const accountB = database.accounts.findOne(
    { _id: "ACCOUNT-B" }
  );

  printjson({ accountA, accountB });

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

Đây là ví dụ minh họa MongoDB transaction trong **mongosh** trên topology hỗ trợ. Trong ứng dụng thực tế, phải xử lý retry transaction theo error labels, unknown commit result và timeout; không đơn giản gọi lại bất kỳ side effect nào ngoài database.

**Read concern trong transaction đặt ở transaction level**, không đặt riêng lẻ cho từng find/aggregate bên trong. Các tùy chọn read concern ở database/collection có thể bị transaction-level concern ghi đè.

### 9.3. Snapshot ngoài transaction (MongoDB 5.0+)

Từ **MongoDB 5.0**, snapshot read concern còn dùng được ở một số read operations **ngoài multi-document transaction**, gồm:

- **find**
- **aggregate**
- **distinct** trên **unsharded collections**

Ví dụ:

~~~javascript
db.runCommand({
  find: "orders",
  filter: {
    tenantId: "SHOP-A"
  },
  readConcern: {
    level: "snapshot"
  },
  maxTimeMS: 10000
});
~~~

Với snapshot read ngoài transaction, dữ liệu trả về thuộc **majority-committed snapshot**. Các commands không thuộc tập hỗ trợ không được tùy ý dùng snapshot concern.

**Đọc một query snapshot ngoài transaction không đồng nghĩa tất cả các query tiếp theo tự có cùng một snapshot T**. Nếu cần nhiều thao tác có chung một point-in-time, phải thiết kế transaction hoặc sử dụng cơ chế snapshot timestamp được hỗ trợ một cách rõ ràng.

### 9.4. atClusterTime: chọn snapshot theo timestamp

Ngoài transaction, MongoDB cho phép chỉ định **atClusterTime** để đọc snapshot tại một timestamp logic cụ thể.

~~~javascript
db.runCommand({
  find: "orders",
  filter: { tenantId: "SHOP-A" },
  readConcern: {
    level: "snapshot",
    atClusterTime: Timestamp(1613577600, 1)
  },
  maxTimeMS: 10000
});
~~~

**Timestamp(1613577600,1) chỉ minh họa cú pháp**, không phải timestamp hợp lệ cho dữ liệu lab hiện tại. Trong hệ thống thực, lấy timestamp thích hợp từ operationTime/clusterTime hoặc response/session theo tài liệu, không bịa timestamp.

Khi server chưa đạt timestamp cần đọc, nó có thể **chờ**; khi snapshot đã quá cũ và không còn nằm trong snapshot history, MongoDB có thể **trả lỗi**.

### 9.5. Snapshot history là hữu hạn

MongoDB lưu history có giới hạn, liên quan **minSnapshotHistoryWindowInSeconds** và tình trạng storage engine. Một snapshot đọc quá lâu hoặc atClusterTime quá cũ có thể bị từ chối/chấm dứt.

Không dùng snapshot read như một cơ chế giữ nguyên dữ liệu lịch sử vô hạn. Nếu cần báo cáo tái lập sau nhiều tháng, nên có **snapshot/archive/versioned data** ở tầng kiến trúc phù hợp.

### 9.6. Snapshot và sự mới nhất

Snapshot của thời điểm T cung cấp tính nhất quán ở T, nhưng **có thể cũ hơn state tại lúc request kết thúc**. Do đó:

~~~text
Snapshot consistency != real-time linearizability
~~~

Snapshot có thể đúng hoàn toàn với dữ liệu tại T nhưng không chứa majority write vừa được xác nhận sau T.

### 9.7. Capped collections và phiên bản

Tài liệu hiện tại nêu từ **MongoDB 8.0** có thể dùng read concern snapshot với capped collections. Một số phiên bản cũ hơn có hạn chế. Khi thiết kế pipeline phụ thuộc snapshot trên capped collection, phải đối chiếu **phiên bản server thực tế**, không suy từ hướng dẫn của phiên bản mới.

## 10. Cùng một timeline, năm mức có thể trả kết quả khác nhau

Giả sử replica set ba thành viên có đơn:

~~~javascript
{
  _id: "ORD-100",
  status: "PENDING"
}
~~~

Write **W1** chuyển status thành PAID:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
);
~~~

Timeline:

~~~text
T0:
  P = PENDING
  S1 = PENDING
  S2 = PENDING

T1: Primary áp dụng W1
  P = PAID
  S1 = PENDING
  S2 = PENDING
  W1 chưa đạt majority commit

T2: S1 áp dụng W1, primary biết W1 đạt majority
  P = PAID
  S1 = PAID
  S2 = PENDING
  majority commit point đã tiến tới W1

T3: S2 đồng bộ và nhận biết majority commit
  P = PAID
  S1 = PAID
  S2 = PAID
~~~

Tại **T1**:

- **local trên P:** có thể trả **PAID**, dù W1 chưa majority committed.
- **local trên S2:** có thể trả **PENDING**.
- **available trên unsharded collection:** tương tự local trên node được chọn.
- **majority:** chỉ trả trạng thái majority committed; ở timeline này có thể là **PENDING**.
- **linearizable:** không thể coi W1 là majority write đã hoàn tất nếu nó chưa majority acknowledged; read có thể cần chờ điều kiện phù hợp. Bảo đảm real-time của linearizable không đồng nghĩa nó phải hiển thị mọi W1 mới áp dụng nhưng chưa hoàn tất.
- **snapshot:** đọc trạng thái của một snapshot majority committed đã được chọn, có thể là **PENDING**.

Tại **T2**:

- **local trên P/S1:** PAID.
- **local trên S2:** PENDING do lag.
- **majority trên P:** có thể trả PAID khi majority view đã tiến tới W1.
- **majority trên S2:** có thể trả PENDING nếu nó chưa áp dụng W1 hoặc chưa có majority view mới.
- **linearizable trên P:** khi W1 là một majority-acknowledged write đã hoàn tất trước lúc read bắt đầu, đọc đơn-document phải phản ánh W1 hoặc state hợp lệ mới hơn.
- **snapshot:** phụ thuộc timestamp snapshot chọn; có thể nhất quán tại thời điểm trước W1 và trả PENDING.

**Không suy ra rằng mọi node ở T2 trả cùng một giá trị.** Replication là bất đồng bộ và các read concerns có mục tiêu khác nhau.

## 11. Read concern và read preference: hai trục lựa chọn độc lập

Read preference thường có các mode:

- **primary** — đọc primary; là mode mặc định thông dụng.
- **primaryPreferred** — ưu tiên primary, có thể fallback secondary trong điều kiện cho phép.
- **secondary** — chỉ đọc secondary.
- **secondaryPreferred** — ưu tiên secondary, có thể fallback primary.
- **nearest** — driver chọn node phù hợp dựa trên latency window và những tiêu chí khác.

### 11.1. Các kết hợp minh họa

| Read preference | Read concern | Tính chất đáng chú ý |
|---|---|---|
| primary | local | Có thể thấy write mới áp dụng nhưng chưa majority commit. |
| secondary | local | Có thể stale do replication lag và có thể thấy dữ liệu rollback. |
| primary | majority | Chỉ majority-committed view, không tự bảo đảm linearizable. |
| secondary | majority | Dữ liệu majority committed nhưng có thể chậm hơn primary. |
| primary | linearizable | Phù hợp khi cần real-time ordering cho query single-document. |
| secondary | linearizable | **Không được hỗ trợ** vì linearizable chỉ ở primary. |
| primary hoặc secondary phù hợp | snapshot ngoài transaction | Snapshot majority committed tại timestamp được chọn. |

Một khi đã đặt readPreference secondary, không thể dùng readConcern majority để **ép read sang primary**; read concern không điều khiển lựa chọn node.

### 11.2. Ví dụ JavaScript diễn giải

~~~javascript
// Mỗi lệnh minh họa mức đọc, không thay đổi read preference.
db.orders.find({ _id: "ORD-100" }).readConcern("local");
db.orders.find({ _id: "ORD-100" }).readConcern("majority");
~~~

Nếu cần điều khiển read preference cho một ứng dụng, có thể cấu hình driver/connection options hoặc collection/database theo API tương ứng. Đừng trông chờ **readConcern("majority")** tự đổi một connection đang ở secondaryPreferred thành primary.

### 11.3. Đọc secondary và yêu cầu freshness

Nếu ứng dụng cần “dữ liệu không cũ hơn 5 giây”, chỉ đặt **readConcern majority** không đủ: secondary vẫn có thể lag hơn 5 giây.

MongoDB có cơ chế **maxStalenessSeconds** trong read preference để hỗ trợ lựa chọn secondary, nhưng nó là **cơ chế ước lượng/phân loại node** theo điều kiện cụ thể, không phải SLA chứng minh từng document đã mới hơn 5 giây. Giá trị tối thiểu được hỗ trợ và các giới hạn phụ thuộc driver/server.

Với yêu cầu độ mới nghiêm ngặt, cần thiết kế consistency riêng, có thể chọn primary, causal consistency hoặc linearizable trong phạm vi phù hợp.

## 12. Read concern và write concern: phối hợp đúng ngữ nghĩa

### 12.1. Write concern w:1

Một write có **w:1** được xác nhận khi primary thỏa điều kiện acknowledgement tương ứng; nó chưa đòi hỏi đa số members đã replicate.

~~~javascript
db.runCommand({
  update: "orders",
  updates: [
    {
      q: { _id: "ORD-100" },
      u: { $set: { status: "PAID" } }
    }
  ],
  writeConcern: { w: 1 }
});
~~~

Nếu write mới được primary áp dụng và chưa đạt majority commit, local read có thể thấy nó, còn majority read có thể vẫn thấy state cũ. Trong một failover thích hợp, write đó có thể rollback.

### 12.2. Write concern majority

~~~javascript
db.runCommand({
  update: "orders",
  updates: [
    {
      q: { _id: "ORD-100" },
      u: { $set: { status: "PAID" } }
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 10000
  }
});
~~~

Server phải thỏa điều kiện majority acknowledgement hoặc trả tình trạng timeout/không thể xác nhận trong hạn. **wtimeout** không mặc nhiên có nghĩa write đã được rollback hoặc chắc chắn chưa áp dụng; trạng thái ghi có thể đã thay đổi dù write concern chưa được thỏa đúng hạn.

### 12.3. Bảng phối hợp

| Read concern | Write concern | Có thể kết luận |
|---|---|---|
| local | w:1 | Có thể thấy write sớm nhưng rủi ro rollback và secondary lag. |
| local | majority | Write đã được majority acknowledged, nhưng local read độc lập vẫn có tính chất theo node. |
| majority | w:1 | Read chỉ hiển thị majority committed, nên một write w:1 mới có thể chưa nhìn thấy. |
| majority | majority | Nền tảng quan trọng cho durability và causal consistency khi dùng session đúng cách. |
| linearizable | majority | Bảo đảm real-time ordering trên document duy nhất khi các điều kiện được đáp ứng. |
| snapshot trong transaction | majority khi commit | Snapshot isolation nhất quán theo semantics transaction, kể cả across shards trong tình huống được hỗ trợ. |

Không nên gọi một sự kết hợp là “mọi read đều mới nhất” nếu thiếu session/read routing, điều kiện truy vấn và các hạn chế topology.

## 13. Causal consistency: read-your-writes không chỉ là readConcern majority

### 13.1. Bốn tính chất nhân quả

MongoDB hỗ trợ **causally consistent sessions** để duy trì thứ tự cho các thao tác có quan hệ nhân quả.

Các bảo đảm thường được mô tả:

1. **Read your writes:** đọc thấy kết quả của write trước đó trong session.
2. **Monotonic reads:** lần đọc sau không quay về trạng thái cũ hơn lần đọc trước trong chuỗi tương ứng.
3. **Monotonic writes:** thứ tự các write trong session được tôn trọng.
4. **Writes follow reads:** write dựa vào read trước tuân theo quan hệ nhân quả tương ứng.

Để bảo đảm đầy đủ các tính chất causal consistency kèm durability trong hướng dẫn MongoDB, cần **read concern majority** và **write concern majority** trong session phù hợp.

### 13.2. Ví dụ luồng xác nhận đơn hàng

~~~text
Client mở session S
     |
     v
Write order.status = PAID với w:majority
     |
     v
Read order trong cùng session S với majority
     |
     v
Read phải tuân thủ quan hệ nhân quả với write trước đó
~~~

Driver có thể thêm **afterClusterTime** vào read concern của các thao tác trong causal session, cho phép secondary chờ đến khi tiến độ replication đáp ứng mốc thời gian cần thiết.

### 13.3. Không tự gán afterClusterTime tùy ý

Với causally consistent session, MongoDB drivers tự quản lý **operationTime/clusterTime** và đưa afterClusterTime thích hợp vào read commands. Không nên tự chèn afterClusterTime bằng một timestamp bịa hoặc dùng nó đồng thời với **atClusterTime** trên cùng snapshot read.

### 13.4. Causal session không tự lan giữa mọi HTTP request

Nếu request A dùng session S1, request B mở session S2 độc lập, không thể chỉ dựa vào cùng user ID để kết luận B sẽ tự nhận quan hệ nhân quả của A.

Muốn truyền causal context qua nhiều client/session, cần cơ chế advance operation time/cluster time theo API và mô hình bảo mật phù hợp. Đừng cache một ClientSession để chia sẻ đồng thời giữa mọi thread hoặc mọi user.

### 13.5. Không trộn linearizable với causal session

Theo tài liệu MongoDB, read concern **linearizable không dùng trong causally consistent sessions**. Nếu yêu cầu đồng thời “read-your-writes across replica set members” và “single-document real-time ordering”, cần phân tích mục tiêu và chọn đúng pattern; không đơn giản bật hai chế độ cùng lúc.

## 14. Read concern trong multi-document transactions

### 14.1. Chỉ các mức được hỗ trợ

Multi-document transactions hỗ trợ:

- **local**
- **majority**
- **snapshot**

**available** và **linearizable** không phải read concern hợp lệ cho một transaction.

Read concern trong transaction được đặt **ở transaction level**. Không đặt read concern riêng ở từng operation bên trong transaction, rồi mong các operation đó có level khác nhau.

### 14.2. local trong transaction

Trên replica set, transaction đọc local có thể quan sát snapshot ở thời điểm transaction được mở; nhưng trên sharded cluster, **local không bảo đảm cùng snapshot giữa các shards**.

Do vậy transaction local không phải lựa chọn mặc định cho cross-shard financial reporting cần consistent point-in-time.

### 14.3. majority trong transaction

Khi transaction commit với write concern **majority**, readConcern majority cung cấp các bảo đảm tương ứng của nó về data majority committed. Nếu commit với write concern yếu, không suy ra tất cả bảo đảm majority read của transaction vẫn giữ nguyên.

### 14.4. snapshot trong transaction

Khi transaction commit bằng write concern majority, read concern snapshot cung cấp góc nhìn majority committed tại một thời điểm nhất quán, kể cả across shards trong trường hợp hỗ trợ.

~~~text
Begin Transaction (snapshot)
          |
          +--> Read collection A at T
          |
          +--> Read collection B at T
          |
          +--> Write (nếu cần)
          |
          v
Commit with w:majority
~~~

Đừng diễn giải transaction snapshot là “không thể xảy ra bất kỳ write conflict/abort nào”. Transaction vẫn có thể thất bại khi dữ liệu bị cập nhật đồng thời, khi thời gian chạy quá dài hoặc trong failover. Ứng dụng phải xử lý retry đúng error labels.

### 14.5. Chi phí transaction

Transaction giữ nhiều trạng thái và resources hơn một thao tác đọc đơn giản:

- Có thời lượng tối đa và timeout.
- Có thể có write conflicts.
- Có thể gây áp lực snapshot history/cache.
- Việc retry có thể thực thi lại callback của ứng dụng.
- Những thao tác tạo collection/index có quy tắc transaction/read concern riêng.

**Không mở transaction trong suốt thời gian người dùng chỉnh sửa form.** Dùng snapshot của dữ liệu khi hiển thị, rồi conditional update/version CAS khi submit; chỉ mở transaction ngắn nếu cần atomicity xuyên documents.

## 15. Snapshot isolation không đồng nghĩa serializable cho mọi workload

Một hiểu nhầm:

> “Tôi đã dùng snapshot read, vậy mọi quyết định nghiệp vụ dựa trên nhiều document đều tự an toàn trước các transaction cạnh tranh.”

Không đủ. Snapshot isolation bảo đảm các thao tác đọc trong phạm vi thích hợp thấy một trạng thái tại T, nhưng **không tự thay thế việc bảo vệ tất cả invariants khi nhiều transaction cùng ra quyết định**.

Ví dụ có hai bác sĩ được phép trực, và quy tắc “ít nhất một người phải trực”. Mỗi transaction:

1. Đọc thấy **A=true, B=true** tại snapshot T.
2. Transaction X chuyển **A=false**.
3. Transaction Y chuyển **B=false**.

Nếu hai transaction ghi vào **hai document khác nhau** mà không tạo xung đột ghi trên cùng document hoặc không mã hóa invariant trong một cơ chế ràng buộc, có thể gặp **write skew** trong những hệ thống dùng snapshot isolation.

~~~text
Snapshot T:
  Doctor A onCall=true
  Doctor B onCall=true

Tx X đọc cả hai -> viết A=false
Tx Y đọc cả hai -> viết B=false

Nguy cơ:
  A=false và B=false
  vi phạm invariant "ít nhất một người trực"
~~~

Giải pháp cần thiết kế theo invariant:

- Đưa điều kiện cần bảo vệ vào **một document/aggregate** có thể cập nhật nguyên tử.
- Thiết kế một **guard document** được các transaction cùng tranh chấp.
- Dùng unique constraints/conditional writes phù hợp.
- Hoặc thiết kế giao thức kiểm soát khác có thể chứng minh đúng.

Đây là vấn đề của **isolation level và cách mã hóa invariant**, không phải lỗi của MongoDB vì đã cho phép dùng snapshot.

## 16. Sharded cluster: orphaned documents và cross-shard snapshots

### 16.1. Local và available khác nhau ở shard ownership

Trong sharded collection, mongos dựa trên metadata để route query. Quá trình chunk migration có thể để lại **orphaned documents** tạm thời trên shard nguồn.

Read concern **available** có thể phục vụ truy vấn khi chưa kiểm chứng được shard ownership do network partition. Theo tài liệu MongoDB, nó có thể trả **orphaned documents** và kết quả không chính xác trong những tình huống đó.

Read concern **local** tránh rủi ro cụ thể này bằng những kiểm tra consistency/routing phù hợp hơn; nó vẫn không bảo đảm majority durability.

### 16.2. Majority không có nghĩa một snapshot cross-shard

Giả sử báo cáo truy vấn dữ liệu trên hai shards:

~~~text
Shard A:
  majority-committed view ở thời điểm T1

Shard B:
  majority-committed view ở thời điểm T2
~~~

Chỉ yêu cầu readConcern majority không tự bảo đảm dữ liệu từ A và B cùng là **một mốc thời gian logic T** cho mọi query/báo cáo.

Nếu cần báo cáo **point-in-time xuyên shards**, chọn **snapshot** trong phạm vi command/transaction được hỗ trợ, đồng thời xét snapshot history và chi phí tài nguyên.

### 16.3. Linearizable trên sharded collection

Linearizable không được coi là giải pháp tổng quát cho một report nhiều shards. Bảo đảm áp dụng cho thao tác đọc được định danh duy nhất một document với yêu cầu primary. Với nghiệp vụ xuyên nhiều documents/shards, cần mô hình dữ liệu, transactions và invariants phù hợp.

### 16.4. Timeouts và network partitions

Khi nhiều shard/node không khả dụng:

- **available** có thể tiếp tục trả kết quả với bảo đảm yếu hơn.
- **majority** có thể chờ hoặc không thể phục vụ view đúng khi quorum/replication gặp vấn đề.
- **linearizable** có thể timeout nếu không xác minh được primary/majority.
- **snapshot** có thể chờ timestamp, timeout hoặc lỗi nếu history không đủ.

Chọn ưu tiên **availability hay consistency** theo loại dữ liệu, không bật available chỉ để “chữa timeout” của một API tài chính.

## 17. Java Sync Driver: đặt read concern đúng phạm vi

MongoDB Java Sync Driver có các hằng:

~~~java
ReadConcern.LOCAL
ReadConcern.AVAILABLE
ReadConcern.MAJORITY
ReadConcern.LINEARIZABLE
ReadConcern.SNAPSHOT
~~~

Read concern có thể được cấu hình ở **MongoClient**, **MongoDatabase** hoặc **MongoCollection** theo API hỗ trợ. Đối tượng collection/database với read concern riêng là **view mới**, không tự thay đổi cấu hình của object gốc.

### 17.1. Ví dụ đọc majority từ collection

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ReadConcernDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "mongo_consistency_lab"
            );

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            MongoCollection<Document> majorityOrders =
                    orders.withReadConcern(ReadConcern.MAJORITY)
                          .withReadPreference(ReadPreference.primary());

            Document order = majorityOrders.find(
                    new Document("_id", "ORD-100")
            ).first();

            System.out.println(order == null ? "Not found" : order.toJson());
        }
    }
}
~~~

Ý nghĩa:

- **withReadConcern(ReadConcern.MAJORITY)** yêu cầu majority-committed view.
- **withReadPreference(ReadPreference.primary())** chọn primary.
- Query với filter **_id** dùng MongoDB Java Driver; không phải transaction.
- **orders** gốc không bị thay đổi bởi các lời gọi **with...**; **majorityOrders** là collection handle cấu hình mới.

**Cảnh báo:** primary + majority không đồng nghĩa mọi read sẽ linearizable. Nếu API cần bảo đảm real-time single-document, phải cân nhắc **LINEARIZABLE** và timeout.

### 17.2. Cấu hình từng mức ở cùng collection

~~~java
MongoCollection<Document> localView =
        orders.withReadConcern(ReadConcern.LOCAL);

MongoCollection<Document> availableView =
        orders.withReadConcern(ReadConcern.AVAILABLE);

MongoCollection<Document> majorityView =
        orders.withReadConcern(ReadConcern.MAJORITY);

MongoCollection<Document> snapshotView =
        orders.withReadConcern(ReadConcern.SNAPSHOT);
~~~

Những handle trên biểu diễn yêu cầu đọc khác nhau. **Không phải mọi level đều hợp lệ cho mọi operation/topology**. Ví dụ snapshot ngoài transaction chỉ dùng với các commands được hỗ trợ trên phiên bản MongoDB phù hợp.

### 17.3. Linearizable với primary và timeout

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> strongSingleDocumentView =
        orders.withReadPreference(ReadPreference.primary())
              .withReadConcern(ReadConcern.LINEARIZABLE);

Document result = strongSingleDocumentView
        .find(new Document("_id", "ORD-100"))
        .maxTime(5, TimeUnit.SECONDS)
        .first();
~~~

**maxTime** đặt giới hạn thời gian phía server cho query. Nếu không thỏa linearizable trong hạn, driver có thể ném exception. Không diễn giải exception như document không tồn tại.

### 17.4. Read preference secondary kết hợp majority

~~~java
MongoCollection<Document> majoritySecondaryView =
        orders.withReadPreference(ReadPreference.secondaryPreferred())
              .withReadConcern(ReadConcern.MAJORITY);

Document order = majoritySecondaryView.find(
        new Document("_id", "ORD-100")
).first();
~~~

Đây là read majority nhưng ưu tiên secondary. **Có thể vẫn stale** do secondary lag; read concern không tự biến secondaryPreferred thành primary.

### 17.5. Kế thừa cấu hình

Một mô hình thông dụng:

~~~text
MongoClient defaults
      |
      v
MongoDatabase settings
      |
      v
MongoCollection settings
      |
      v
Read operation

Transaction options có precedence riêng
khi thao tác nằm trong transaction.
~~~

Nếu cấu hình collection khác client, collection handle dùng setting cụ thể của nó cho những thao tác ngoài transaction. Bên trong transaction, **transaction-level read concern** là cấu hình cần quan tâm. Vì vậy đừng suy luận từ một collection handle mà bỏ qua session/transaction context.

## 18. Java Sync Driver: causally consistent session

Khi cần đọc thấy một write trước đó trong chuỗi thao tác có quan hệ nhân quả, dùng client session với read/write concern majority:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoClient;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public final class CausalSessionExample {
    public static void run(MongoClient client) {

        MongoCollection<Document> orders = client
                .getDatabase("mongo_consistency_lab")
                .getCollection("orders")
                .withReadConcern(ReadConcern.MAJORITY)
                .withWriteConcern(WriteConcern.MAJORITY);

        ClientSessionOptions options = ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

        try (ClientSession session = client.startSession(options)) {
            orders.updateOne(
                    session,
                    eq("_id", "ORD-100"),
                    set("status", "PAID")
            );

            Document updated = orders.find(
                    session,
                    eq("_id", "ORD-100")
            ).first();

            System.out.println(updated);
        }
    }
}
~~~

Điều cần nhớ:

1. Các thao tác cần dùng **cùng ClientSession**.
2. Read concern majority và write concern majority hỗ trợ bộ bảo đảm causal consistency đầy đủ theo tài liệu.
3. Driver quản lý operation time/cluster time, không tự chèn timestamp tùy ý.
4. Không chạy nhiều thao tác đồng thời trên **cùng ClientSession** từ nhiều threads; driver/session có ràng buộc concurrency riêng.
5. Causal session không thay thế transaction khi cần commit nhiều document cùng nhau.

### 18.1. Session có phải transaction không?

**Không.** Một session có thể thực hiện nhiều thao tác mà không mở transaction. Causal consistency là bảo đảm về thứ tự các thao tác có quan hệ nhân quả; transaction là cơ chế nhóm những thao tác database vào một đơn vị commit/abort.

~~~text
Causal session:
  Read/Write A -> Read/Write B
  B tôn trọng quan hệ nhân quả với A

Transaction:
  Begin -> Operations -> Commit/Abort
  Có phạm vi atomic commit và isolation riêng
~~~

## 19. Java Sync Driver: transaction với snapshot

Ví dụ đọc hai accounts trong cùng transaction:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;

public final class SnapshotTransactionExample {

    public static void run(MongoClient client) {
        MongoCollection<Document> accounts = client
                .getDatabase("mongo_consistency_lab")
                .getCollection("accounts");

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.startTransaction(options);

            try {
                Document accountA = accounts
                        .find(session, eq("_id", "ACCOUNT-A"))
                        .first();

                Document accountB = accounts
                        .find(session, eq("_id", "ACCOUNT-B"))
                        .first();

                System.out.println(accountA);
                System.out.println(accountB);

                session.commitTransaction();
            } catch (RuntimeException ex) {
                session.abortTransaction();
                throw ex;
            }
        }
    }
}
~~~

Đây là ví dụ tối giản để thấy **TransactionOptions.readConcern(SNAPSHOT)** và **writeConcern(MAJORITY)**. Không phải mẫu transaction retry đầy đủ.

Trong production:

- Chỉ sử dụng transactions trên deployment hỗ trợ.
- Xử lý **TransientTransactionError** và **UnknownTransactionCommitResult** theo retry guidelines/driver helpers.
- Không chạy side effects ngoài MongoDB trong transaction callback nếu chúng có thể bị lặp.
- Giới hạn thời gian, số thao tác và kích thước dữ liệu trong transaction.
- Đừng đặt một readConcern khác cho từng find rồi kỳ vọng override transaction-level snapshot.

## 20. Spring Data MongoDB: sử dụng concern và transaction

Spring Data MongoDB dựa trên MongoDB Java Driver, vì vậy các khái niệm read concern/read preference/write concern vẫn giữ nguyên.

### 20.1. Cấu hình transaction manager với snapshot

Ví dụ cấu hình bằng Java:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return new MongoTransactionManager(factory, options);
    }
}
~~~

Việc khai báo **MongoTransactionManager** cho phép Spring quản lý transaction trong những service có cấu hình transaction hợp lệ.

### 20.2. Đọc trong @Transactional

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountReportService {

    private final MongoTemplate mongoTemplate;

    public AccountReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional(readOnly = true)
    public long readTotalBalance() {
        Document a = mongoTemplate.findOne(
                Query.query(
                        Criteria.where("_id").is("ACCOUNT-A")
                ),
                Document.class,
                "accounts"
        );

        Document b = mongoTemplate.findOne(
                Query.query(
                        Criteria.where("_id").is("ACCOUNT-B")
                ),
                Document.class,
                "accounts"
        );

        long aBalance = a == null ? 0L
                : ((Number) a.get("balance")).longValue();

        long bBalance = b == null ? 0L
                : ((Number) b.get("balance")).longValue();

        return aBalance + bBalance;
    }
}
~~~

Ví dụ giả định field balance có BSON numeric type tương thích, và hai account missing được domain cho phép coi là 0; trong ứng dụng tài chính thật, **không nên tự mặc định missing account = 0** nếu đó là trạng thái lỗi. Mục tiêu minh họa là hai reads tham gia transaction do Spring quản lý.

**Chú ý:** **@Transactional(readOnly=true)** là hint và vẫn có thể mở transaction với MongoDB trong cấu hình tương ứng. Read concern thực tế do transaction manager/options và các overrides quyết định, không phải chỉ bởi tên annotation.

### 20.3. Không nhầm raw driver collection với transaction của MongoTemplate

~~~java
mongoTemplate.getCollection("orders")
        .withReadConcern(ReadConcern.MAJORITY);
~~~

Lời gọi này lấy một collection handle của **native driver** với read concern majority. Nếu tự gọi raw driver operations mà không truyền đúng session của transaction đang được Spring quản lý, bạn có thể đi ra ngoài ranh giới transaction mong muốn. Khi cần transaction, dùng APIs Spring Data đã liên kết session hoặc tích hợp client session đúng theo hướng dẫn.

### 20.4. Cấu hình read concern khác nhau theo use case

Trong ứng dụng có nhiều endpoint, thường không nên đặt **LINEARIZABLE** toàn cục chỉ vì một API cần nó.

Gợi ý thiết kế:

- Repository đọc bảng danh sách thông thường: read concern theo SLA và data sensitivity.
- Service điều phối trạng thái một document: native driver handle LINEARIZABLE + maxTimeMS khi cần.
- Service giao dịch nhiều documents: MongoTransactionManager với SNAPSHOT + majority commit.
- Service có causal chain: ClientSession/driver APIs tương ứng.

Cần ghi rõ mỗi endpoint yêu cầu **consistency property nào**, thay vì chỉ lặp một cấu hình ngầm cho mọi thao tác.

## 21. Cấu hình mặc định và precedence

MongoDB cho phép cấu hình **global default read concern** và **global default write concern** cho replica sets/sharded clusters thông qua các cơ chế quản trị phù hợp.

Mặc định khi không cấu hình override, read concern cho primary/secondary thường là **local**, nhưng **không được luôn giả định local** trên deployment có custom default hoặc connection settings.

Các nguồn cấu hình có thể gồm:

1. Default phía deployment.
2. MongoClient settings hoặc connection string.
3. MongoDatabase handle.
4. MongoCollection handle.
5. Transaction options khi thao tác thuộc transaction.

### 21.1. Kiểm tra deployment

Với quyền quản trị thích hợp:

~~~javascript
db.adminCommand({
  getDefaultRWConcern: 1
});
~~~

Response có thể cho biết default read/write concerns và nguồn của các thiết lập. Tên trường và cách hiển thị có thể khác theo MongoDB version/deployment.

Không tự sửa global defaults chỉ để thử nghiệm một API: thay đổi này có thể ảnh hưởng nhiều ứng dụng.

### 21.2. Cấu hình tập trung nhưng cho phép override có kiểm soát

Một chính sách vận hành có thể:

- Đặt default phù hợp với đại đa số workload.
- Yêu cầu những reads quan trọng dùng explicit concern ở tầng repository/service.
- Gắn timeout với reads có thể chờ lâu.
- Ghi log/metrics cho các mức concern đặc biệt.
- Xác nhận driver và topology hỗ trợ level được chọn.

Đừng phụ thuộc hoàn toàn vào thông số ngầm nếu một endpoint có contract consistency nghiêm ngặt.

## 22. Chọn read concern theo yêu cầu nghiệp vụ

### 22.1. Trang danh sách sản phẩm

Yêu cầu:

- Người dùng xem tên, ảnh và mô tả sản phẩm.
- Chấp nhận một số cập nhật mới xuất hiện chậm.
- Cần throughput cao và độ trễ thấp.

Lựa chọn có thể là **local** với read preference phù hợp. Nếu những dữ liệu hiển thị bắt buộc tránh rollback, cân nhắc **majority**.

Không cần mặc định dùng **linearizable** cho cả danh sách vì nó không cung cấp một linearizable snapshot toàn collection.

### 22.2. Xác nhận thanh toán

Yêu cầu:

- Chỉ hiển thị PAID khi trạng thái ghi đã đủ bền vững theo chính sách.
- Không được xác nhận thanh toán chỉ vì một local write chưa được majority commit.

Một thiết kế có thể:

1. Ghi trạng thái với **writeConcern majority**.
2. Đọc bằng **readConcern majority** hoặc causal session nếu cần read-your-writes.
3. Khi cần xác minh trạng thái **một document** theo thứ tự real-time, cân nhắc **linearizable** trên primary.
4. Thiết kế idempotency và integration với payment provider.

Không được dùng **chỉ một majority read** làm bằng chứng đã thu tiền ở bên thứ ba. Trạng thái thanh toán cần được xác nhận theo protocol nghiệp vụ và nguồn authoritative.

### 22.3. Kiểm tra feature flag hoặc trạng thái leader

Yêu cầu:

- Một majority write thay đổi flag/leader đã hoàn tất.
- Read bắt đầu sau đó cần phản ánh trạng thái mới theo real-time.
- Document có một key duy nhất.

**linearizable + primary + maxTimeMS** có thể là lựa chọn thích hợp.

Tuy nhiên cần kết hợp **conditional writes**, lease/fencing token và xử lý timeout. Nếu read không thể xác minh trong thời gian quy định, chọn fallback theo nguyên tắc an toàn của hệ thống.

### 22.4. Báo cáo doanh thu nhiều collections

Yêu cầu:

- Tổng đơn hàng, chi tiết payments và hoàn tiền phải thuộc cùng một điểm nhìn.
- Có thể chấp nhận snapshot chậm hơn state hiện tại một ít.

**snapshot** trong transaction hoặc snapshot read phù hợp với phạm vi thao tác là lựa chọn đáng xem xét.

Không sử dụng linearizable cho một find đơn-document rồi suy rằng toàn báo cáo nhiều collections cũng linearizable.

### 22.5. Dashboard không yêu cầu tuyệt đối chính xác

Yêu cầu:

- Thống kê gần thời gian thực.
- Chấp nhận dữ liệu chậm một ít hoặc tự làm mới.

Có thể dùng **local** hoặc **majority** tùy yêu cầu không rollback. Nếu đọc secondary, phải chấp nhận replication lag.

**available** chỉ nên cân nhắc khi chấp nhận rủi ro đặc thù của sharded cluster và thật sự cần ưu tiên availability cao hơn tính chính xác.

### 22.6. Đọc lại thay đổi vừa lưu trong cùng phiên làm việc

Yêu cầu:

- Người dùng nhấn Save thành công.
- Ngay sau đó, cùng workflow muốn đọc lại trạng thái vừa ghi.

Sử dụng **causally consistent session + majority read/write** là lựa chọn chuẩn khi cần bảo đảm causal consistency xuyên replica set members. Nếu dùng primary và cùng request, vẫn phải hiểu failover, cache, session boundaries và durability requirements.

### 22.7. Dữ liệu cache hoặc dữ liệu chấp nhận stale

Nếu response có cache TTL hoặc business rule cho phép stale, read concern mạnh hơn không tự làm cache hết stale. Cần xác định:

- Cache có thể chậm tối đa bao lâu?
- Cache invalidation hoạt động như thế nào?
- Read từ secondary có tạo thêm lag ngoài cache hay không?
- Mức độ rollback có ảnh hưởng quyết định nghiệp vụ hay chỉ hiển thị?

**Consistency của database và freshness của cache là hai vấn đề khác nhau.**

## 23. Cây quyết định lựa chọn read concern

~~~text
Bạn cần đọc cái gì?
        |
        +-- Cần một point-in-time nhất quán
        |   cho nhiều document / nhiều shard?
        |         |
        |         +-- CÓ --> SNAPSHOT
        |         |          + transaction nếu cần nhiều lệnh
        |         |          + majority commit và giới hạn history
        |         |
        |         +-- KHÔNG
        |               |
        |               v
        +-- Cần real-time order đối với một
        |   document định danh duy nhất?
        |         |
        |         +-- CÓ --> LINEARIZABLE
        |         |          + PRIMARY
        |         |          + maxTimeMS
        |         |          + majority writes
        |         |
        |         +-- KHÔNG
        |               |
        |               v
        +-- Có cần tránh dữ liệu có thể rollback?
        |         |
        |         +-- CÓ --> MAJORITY
        |         |          + causal session nếu cần
        |         |            read-your-writes
        |         |
        |         +-- KHÔNG
        |               |
        |               v
        +-- Có chấp nhận stale/rollback?
                  |
                  +-- CÓ --> LOCAL
                  |
                  +-- Nếu sharded partition và cần
                      availability cực cao dù có
                      rủi ro orphaned documents
                           |
                           +-- AVAILABLE
~~~

Đây là **hướng dẫn tư duy**, không phải thay thế việc đọc tài liệu version và kiểm thử workload. Có thể một API có nhiều yêu cầu đồng thời như timeout, authorization, write concern và cross-document invariants cần kiến trúc bổ sung ngoài một read concern.

## 24. Những hiểu nhầm thường gặp

### 24.1. “Read concern majority đọc bản mới nhất”

**Sai.** Majority chỉ trả data majority committed. Một secondary hoặc majority view chưa theo kịp vẫn có thể trả bản cũ.

Muốn real-time ordering trên một document, xem linearizable; muốn read-your-writes theo causal chain, xem causal session.

### 24.2. “Chọn primary là đủ để bảo đảm linearizable”

**Sai.** Trong một số network partitions, node primary cũ có thể tạm chưa nhận ra mình đã mất vai trò và có thể phục vụ dữ liệu stale. Linearizable yêu cầu xác minh bổ sung và chỉ có bảo đảm đúng với query shape phù hợp.

### 24.3. “Read concern local đồng nghĩa chỉ đọc từ local machine”

**Sai.** local không chỉ định đọc node nào. **Read preference** mới điều khiển primary/secondary. local mô tả dữ liệu có thể đọc trên node đã được chọn.

### 24.4. “Available giống majority nhưng nhanh hơn”

**Sai.** Available có bảo đảm dữ liệu yếu hơn, có thể rollback và trên sharded cluster có thể trả orphaned documents.

### 24.5. “Available luôn là cách nhanh nhất cho mọi deployment”

Không nên khái quát. Trên unsharded collection, available và local tương đương về semantics. Hiệu năng thực tế phụ thuộc network, query plan, cache, replication và topology; không chỉ tên read concern.

### 24.6. “WriteConcern majority tự khiến mọi read đều majority”

**Sai.** Write concern và read concern là hai cấu hình khác nhau. Read vẫn dùng level mặc định/override của nó.

### 24.7. “Majority luôn bảo đảm đọc được write tôi vừa gửi từ một session mới”

Không nhất thiết. Để có **read-your-writes** trong chuỗi nhân quả, cần xem **causal session** với majority read/write hoặc các bảo đảm khác của routing/protocol. Một session mới độc lập không tự kế thừa causal context.

### 24.8. “Linearizable áp dụng cho aggregate toàn collection”

Không được dựa vào bảo đảm linearizable cho hàng nghìn documents trong cùng báo cáo. Theo MongoDB, bảo đảm chỉ áp dụng với query filter định danh duy nhất một document và các điều kiện search key tương ứng.

### 24.9. “Linearizable không cần timeout vì mong muốn consistency mạnh”

Ngược lại, vì cần xác minh điều kiện majority và primary, MongoDB khuyến nghị **luôn dùng maxTimeMS**. Khi không thể đáp ứng, trả lỗi timeout chứ không suy ra dữ liệu absent.

### 24.10. “Snapshot lúc nào cũng là dữ liệu mới nhất”

**Sai.** Snapshot có thể ở thời điểm T trong quá khứ. Nó bảo đảm point-in-time view, không bảo đảm real-time recency.

### 24.11. “Snapshot ngoài transaction trên một query tự áp dụng cho các query sau”

Không mặc định. Muốn nhiều reads cùng timestamp cần transaction hoặc quản lý snapshot timestamp theo API hỗ trợ.

### 24.12. “Có snapshot transaction thì mọi invariant xuyên document tự an toàn”

Snapshot isolation không tự biến mọi workload thành serializable. Cần thiết kế guard documents, write conflicts, conditional writes hoặc business protocol cho invariants xuyên documents.

### 24.13. “Có thể đặt readConcern khác nhau cho từng find bên trong transaction”

Không. Read concern được đặt ở **transaction level**. MongoDB không cho phép dùng tùy ý mọi level trên từng operation trong transaction.

### 24.14. “Causal session và transaction là một”

Không. Causal session giữ thứ tự nhân quả; transaction có commit/abort và isolation theo mức được chọn. Một causal session không tự atomic commit nhiều writes.

### 24.15. “Thấy PAID bằng local nghĩa là không thể rollback”

Không. Dữ liệu mới áp dụng cục bộ có thể chưa majority committed và có thể bị rollback trong tình huống failover thích hợp.

### 24.16. “Read concern chữa được query chậm do thiếu index”

Không. Read concern không thay thế index, query optimization hoặc data modeling. Một query COLLSCAN vẫn có thể chậm ở mọi level.

### 24.17. “Read concern chữa được double charge”

Không. Double charge thường liên quan idempotency, giao thức với payment provider, retries và atomicity nghiệp vụ. Read concern chỉ là một thành phần trong tính nhất quán dữ liệu đọc.

## 25. Giám sát và kiểm thử lựa chọn read concern

### 25.1. Quan sát replication

Trong mongosh, với quyền phù hợp:

~~~javascript
rs.status();
~~~

Quan sát trạng thái primary/secondaries, thông tin tiến độ replication và tình trạng thành viên. Không dựa duy nhất vào một lần rs.status trong production; dùng hệ thống giám sát có thu thập metrics theo thời gian.

Ở MongoDB Atlas hoặc managed service, có thể dùng dashboard/provider metrics tương ứng cho replication lag, node availability, read/write latency.

### 25.2. Theo dõi các chỉ số

| Metric | Ý nghĩa |
|---|---|
| **Secondary replication lag** | Rủi ro stale reads, đặc biệt khi readPreference chọn secondary. |
| **Majority commit point progress** | Khả năng đọc những writes đã majority committed. |
| **Read latency p95/p99 theo level** | Tác động latency khi dùng majority/linearizable/snapshot. |
| **Timeouts/maxTimeMS errors** | Query không hoàn thành trong giới hạn hoặc consistency không thể được thỏa. |
| **Primary elections/failovers** | Bối cảnh rollback/stale primary và availability. |
| **Transaction abort/retry rate** | Tải concurrency và snapshot transaction behavior. |
| **SnapshotTooOld/history errors** | Snapshot T quá cũ hoặc operation kéo dài. |
| **Sharded chunk migrations** | Bối cảnh orphaned documents và routing consistency. |

Tên metric cụ thể phụ thuộc server version, telemetry provider và driver. Hãy map chúng với nguồn observability thực tế.

### 25.3. Test read concern local trước failover

Trên môi trường test replica set có thể điều phối failover:

1. Ghi dữ liệu theo write concern yếu như w:1.
2. Tạo điều kiện replication lag/thành viên chậm có kiểm soát.
3. Đọc local trên primary hoặc secondary.
4. Quan sát khác biệt trước khi W1 majority committed.
5. Kích hoạt failover **trên môi trường thử nghiệm được phép**.
6. Quan sát khả năng dữ liệu chưa majority committed rollback.

Không cố phá replication/primary production chỉ để kiểm thử bài học.

### 25.4. Test majority và secondary lag

1. Ghi một document với w:"majority".
2. Đọc từ primary với majority.
3. Đọc từ secondary với majority.
4. Quan sát rằng secondary có thể trễ trong việc nhận biết/thể hiện W1.
5. So sánh với casual session theo một chuỗi read-after-write.

**Đừng viết assertion “secondary majority phải lập tức thấy W1 sau đúng N ms”** nếu không có bảo đảm về lag/timeout tương ứng.

### 25.5. Test linearizable

1. Ghi một field trên document định danh bằng _id với w:"majority".
2. Sau khi write đã được xác nhận, đọc bằng linearizable trên primary với maxTimeMS.
3. Kiểm tra kết quả phản ánh write đó hoặc state hợp lệ mới hơn.
4. Khi không còn quorum, kiểm tra read có thể timeout và ứng dụng xử lý lỗi khác với “không tồn tại”.

### 25.6. Test snapshot

1. Tạo hai documents với state có thể kiểm tra tổng.
2. Trong transaction có snapshot read concern, đọc cả hai.
3. Trong một luồng khác, cập nhật state có chủ đích.
4. Kiểm tra read trong snapshot không trộn tùy ý dữ liệu từ các thời điểm khác nhau.
5. Kiểm tra transaction có thể gặp conflict/abort khi có concurrent writes phù hợp.

Với sharded setup, cần kiểm thử nhiều shards và snapshot history; không chỉ dùng standalone local.

## 26. Bài thực hành

### Bài 1 — Phân biệt ba cấu hình

Giải thích mỗi cấu hình sau điều khiển điều gì:

~~~text
readPreference = secondary
readConcern = majority
writeConcern = majority
~~~

Vì sao readConcern majority không buộc driver đọc primary?

### Bài 2 — local trên primary và secondary

Một write W1 đã áp dụng trên primary nhưng chưa replicate đến secondary. Dự đoán local read trên hai node có thể trả khác nhau như thế nào.

### Bài 3 — rollback

W1 chỉ được w:1 xác nhận rồi primary bị failover trước majority commit. Local read trước failover đã trả W1. Vì sao điều đó không mâu thuẫn với MongoDB atomicity?

### Bài 4 — available và orphaned document

Mô tả một chunk đang migrate từ Shard A sang Shard B, có network partition. Vì sao available có thể trả dữ liệu từ shard không còn sở hữu chunk? Trong trường hợp nào nên tránh available?

### Bài 5 — majority có phải luôn mới nhất?

Primary đã xác nhận W1 theo majority, nhưng một secondary lag chưa thể phục vụ W1. Nếu đọc majority trên secondary đó, có thể thấy trạng thái cũ không? Giải thích.

### Bài 6 — linearizable và real-time

Một write w:"majority" vào **{_id:"flag.checkout"}** đã hoàn tất. Một read linearizable bắt đầu sau đó. Bảo đảm nào ứng dụng có thể kỳ vọng? Vì sao nên dùng maxTimeMS?

### Bài 7 — Tại sao linearizable yêu cầu query một document?

So sánh:

~~~javascript
db.flags.find(
  { _id: "checkout.enabled" }
).readConcern("linearizable").maxTimeMS(5000);
~~~

với:

~~~javascript
db.flags.find(
  { status: "ACTIVE" }
).readConcern("linearizable").maxTimeMS(5000);
~~~

Vì sao không nên áp dụng bảo đảm của truy vấn đầu cho cả tập document của truy vấn sau?

### Bài 8 — Snapshot nhiều documents

Hai accounts được cập nhật trong một transaction chuyển tiền. Hãy giải thích vì sao báo cáo đọc cả hai ở một snapshot T phù hợp hơn các lần đọc độc lập ở những thời điểm khác nhau.

### Bài 9 — Snapshot không đồng nghĩa dữ liệu mới nhất

Một snapshot được chọn tại T. Write W2 majority commit ở T+1. Snapshot T có bắt buộc trả W2 không? Giải thích.

### Bài 10 — atClusterTime

Viết lệnh **find** với read concern snapshot và atClusterTime (dùng timestamp hợp lệ lấy từ server thực). Nêu hai tình huống server có thể chờ hoặc báo lỗi.

### Bài 11 — Causal consistency

Viết pseudo-code:

~~~text
start session
write with majority
read with majority in same session
end session
~~~

Nêu ý nghĩa của afterClusterTime được driver thêm tự động và vì sao mở một session mới độc lập không tự kế thừa causal context.

### Bài 12 — Java Driver

Từ MongoCollection<Document>, tạo:

- Một handle read concern majority, read preference secondaryPreferred.
- Một handle read concern linearizable, read preference primary.
- Một lệnh find đơn-document với maxTime 5 giây.

### Bài 13 — Transaction trong Java

Tạo TransactionOptions có:

~~~java
ReadConcern.SNAPSHOT
WriteConcern.MAJORITY
ReadPreference.primary()
~~~

Giải thích vì sao không nên đặt read concern riêng cho find bên trong transaction.

### Bài 14 — Chọn concern cho từng API

Ánh xạ những yêu cầu sau sang một hoặc nhiều cơ chế phù hợp:

1. Danh sách sản phẩm chấp nhận stale.
2. Kiểm tra flag một document sau majority write.
3. Báo cáo tài chính nhiều documents tại cùng thời điểm.
4. Read-your-writes qua secondary trong cùng phiên làm việc.
5. Dashboard sharded ưu tiên availability dù có nguy cơ orphaned records.

Với mỗi lựa chọn, nêu ít nhất một hạn chế.

### Bài 15 — Cấu hình mặc định

Giải thích vì sao một deployment đã chỉnh global default read concern có thể khác giả định của ứng dụng. Dùng getDefaultRWConcern để quan sát nếu có quyền.

### Bài 16 — Kiểm thử failover

Đề xuất test plan kiểm chứng readConcern local, majority và linearizable trong môi trường replica set thử nghiệm. Chỉ ra cách phân biệt **timeout** với **document không tồn tại**.

## 27. Câu hỏi ôn tập

1. Read concern dùng để điều khiển điều gì?
2. Read concern khác read preference ra sao?
3. Read concern khác write concern ra sao?
4. local có phải luôn đọc primary không?
5. Vì sao local có thể trả write bị rollback?
6. available khác local đáng kể nhất ở tình huống nào?
7. Orphaned document là gì, và available có thể làm lộ nó ra sao?
8. majority bảo đảm loại dữ liệu nào được trả về?
9. Majority read trên secondary có thể stale không?
10. Vì sao majority không tự đồng nghĩa linearizable?
11. Linearizable phản ánh những writes nào đã hoàn tất trước khi read bắt đầu?
12. Linearizable có yêu cầu primary không?
13. Vì sao cần query filter định danh duy nhất một document cho bảo đảm linearizable?
14. Vì sao linearizable nên có maxTimeMS?
15. Snapshot bảo đảm tính chất gì mà majority đơn thuần không tự bảo đảm?
16. Snapshot có luôn chứa write majority mới nhất không?
17. Từ MongoDB 5.0, những read operations nào hỗ trợ snapshot ngoài transaction?
18. atClusterTime khác afterClusterTime ra sao?
19. Snapshot history hữu hạn tạo ra những lỗi nào?
20. Multi-document transaction hỗ trợ những read concern levels nào?
21. Tại sao transaction-level concern quan trọng hơn concern riêng ở collection?
22. Causal consistency gồm bốn tính chất thường được nêu là gì?
23. Cần phối hợp read/write concern thế nào để có causal consistency đầy đủ kèm durability?
24. Tại sao một causal session không phải một transaction?
25. Vì sao snapshot isolation không tự bảo đảm mọi business invariant là serializable?
26. Với Spring Data MongoDB, cần chú ý gì khi dùng MongoTransactionManager và raw driver collection?
27. Làm sao chọn level cho API danh sách sản phẩm, API kiểm tra leader và API báo cáo tài chính?

## 28. Tổng kết

Năm read concerns của MongoDB không phải năm mức “nhanh đến chậm” đơn giản, mà biểu diễn những mục tiêu consistency khác nhau:

~~~text
local
  -> Dữ liệu cục bộ của node được chọn.
  -> Có thể stale và rollback.

available
  -> Ưu tiên availability đặc biệt trên sharded cluster.
  -> Có thể trả orphaned documents khi partition/migration.

majority
  -> Chỉ trả dữ liệu majority committed.
  -> Bảo vệ rollback theo cơ chế bình thường.
  -> Không bảo đảm luôn freshest.

linearizable
  -> Real-time ordering với majority writes cho
     truy vấn định danh duy nhất một document.
  -> Primary only, thêm latency và cần maxTimeMS.

snapshot
  -> Góc nhìn point-in-time majority committed.
  -> Hữu ích cho transaction/báo cáo nhiều documents,
     kể cả across shards trong trường hợp hỗ trợ.
  -> Có thể ở quá khứ, giới hạn snapshot history.
~~~

**Những nguyên tắc cần ghi nhớ:**

1. Luôn phân biệt **đọc từ node nào (read preference)**, **đọc mức dữ liệu nào (read concern)** và **ghi xác nhận khi nào (write concern)**.
2. **majority** cho durability của dữ liệu được đọc, nhưng không tự tạo real-time ordering.
3. **linearizable** hướng tới thứ tự real-time đối với một document duy nhất, phải dùng primary và timeout.
4. **snapshot** hướng tới góc nhìn nhất quán tại một timestamp, không phải bản mới nhất.
5. **available** là lựa chọn chấp nhận consistency yếu hơn, đặc biệt cần dè chừng orphaned documents trên sharded cluster.
6. **Causal session + majority read/write** giúp các thao tác có quan hệ nhân quả quan sát đúng thứ tự.
7. **Transaction-level read concern** quyết định isolation trong transaction; không đặt read concern khác nhau trên từng operation.
8. Tùy yêu cầu nghiệp vụ, vẫn cần **unique index, conditional writes, transactions, idempotency, cache invalidation** và kiểm thử failover.

### Tài liệu chính thức MongoDB

- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — tổng quan các mức và khả năng sử dụng.
- [Read Concern "local"](https://www.mongodb.com/docs/manual/reference/read-concern-local/) — local view và rollback.
- [Read Concern "available"](https://www.mongodb.com/docs/manual/reference/read-concern-available/) — availability, sharded cluster và orphaned documents.
- [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/) — majority commit, durability và lag.
- [Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/) — real-time ordering, single-document, primary, maxTimeMS.
- [Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — point-in-time, atClusterTime và snapshot history.
- [MongoDB Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — primary/secondary/nearest và routing.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — w:1, majority và acknowledgement.
- [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — stale reads, causal consistency và isolation.
- [Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/) — các bảo đảm trong client sessions.
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction read concern và commit write concern.
- [MongoDB Java Sync Driver: CRUD Settings](https://www.mongodb.com/docs/drivers/java/sync/current/crud/crud-settings/) — withReadConcern/withReadPreference/withWriteConcern.
- [MongoDB Java Sync Driver: Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — session, TransactionOptions và retry.
- [Spring Data MongoDB: Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager và Spring transaction behavior.

Khi thiết kế một lần đọc MongoDB, câu hỏi quan trọng nhất không phải “level nào mạnh nhất”, mà là **“ứng dụng cần bảo đảm chính xác điều gì về dữ liệu được quan sát?”**. Nếu cần tránh rollback, cân nhắc **majority**; nếu cần real-time order cho một document, dùng **linearizable**; nếu cần một điểm nhìn nhất quán xuyên nhiều documents/shards, dùng **snapshot**. Chọn theo yêu cầu và kiểm chứng với topology, phiên bản và workload thực tế.



