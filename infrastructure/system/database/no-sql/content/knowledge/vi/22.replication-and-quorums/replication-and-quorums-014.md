# Kiểm chứng phạm vi dữ liệu có thể mất khi một miền lỗi gặp sự cố

Một cụm NoSQL có ba replica, một bảng điều khiển báo “healthy”, và ứng dụng vừa nhận phản hồi ghi thành công. Ngay sau đó, một máy, một vùng sẵn sàng (Availability Zone, AZ) hoặc toàn bộ region ngừng hoạt động. **Dữ liệu nào thực sự còn?** Ba replica có nằm ở ba miền lỗi độc lập hay cùng một máy chủ vật lý? “Write acknowledged” nghĩa là đã được xử lý trong RAM, đã được ghi vào journal bền, hay đã tồn tại trên một quorum? Nếu chuyển vùng ghi, liệu một bản sao cũ có thể được chọn làm nguồn dữ liệu mới?

Đây là bài toán **kiểm chứng phạm vi dữ liệu có thể mất** (data-loss exposure) trong chương **Sao chép và quorum** của Database No SQL. Mục tiêu không phải chỉ học cấu hình replication factor, mà là dựng được một **hợp đồng bảo vệ dữ liệu** và kiểm tra nó bằng số liệu, dấu mốc phiên bản, thử lỗi có kiểm soát và khôi phục thực tế.

Bài học bao gồm:

- Phân biệt process, node, rack, AZ, region, provider/account và các miền lỗi chung.
- Hiểu acknowledged, committed, replicated, journaled, durable, visible và backed up là những mốc khác nhau.
- Xác định rủi ro mất dữ liệu trong replication đồng bộ/bất đồng bộ và các mức quorum.
- Tính khoảng mất dữ liệu theo **dấu mốc ghi** và thời gian, không chỉ nhìn replica count.
- Kiểm tra các kịch bản leader failure, mất AZ, mất region, phân vùng mạng, failover và restore.
- Thiết kế thí nghiệm có kiểm soát, phân loại dữ liệu **đã ACK mà mất**, **đã nhận chưa ACK**, **bản sao lệch** và **side effect ở hệ ngoài**.
- Chọn biện pháp giảm RPO phù hợp với từng nhóm nghiệp vụ.

**Lưu ý:** Các ví dụ MongoDB, Cassandra/ScyllaDB, Redis và DynamoDB dưới đây là cách đặt câu hỏi theo đặc điểm của từng hệ; chi tiết cam kết phụ thuộc sản phẩm, phiên bản, deployment, storage engine, driver, consistency level, write concern và chế độ replication. Các con số thí nghiệm đều là giả định minh họa. Không thực hiện thử tắt node, chặn mạng hoặc xóa dữ liệu trên production để kiểm tra giả thuyết.

## 1. “Mất dữ liệu” phải được định nghĩa chính xác

Đừng bắt đầu bằng câu “Nếu một AZ chết, có mất dữ liệu không?” khi chưa xác định **dữ liệu nào** và **điểm thời gian nào được dùng làm mốc**.

Có ít nhất sáu tập dữ liệu khác nhau:

| Tập | Ví dụ | Có thể mất mà vi phạm hợp đồng không? |
|---|---|---|
| Request mới đến ứng dụng | HTTP POST đã tới load balancer | Chưa thể biết: có thể chưa có giao dịch nào bắt đầu |
| Write đã nhận để xử lý | Server nhận command nhưng chưa commit | Tùy contract; cần retry/outcome lookup |
| Write đã được database ACK | Driver nhận success theo write concern cụ thể | Nếu mất, có thể vi phạm RPO/durability đã hứa |
| Write đã được replica khác áp dụng | Một follower có bản mới | Chưa chắc bản đó được flush bền hoặc có thể trở thành leader |
| Write đã hiển thị khi đọc | GET thấy version mới | Visibility không tự đồng nghĩa persistence dài hạn |
| Write đã có trong backup/PITR | Có restore point chứa dữ liệu | Khả năng restore còn tùy retention, log và tính nhất quán |

Một dữ liệu chưa được ACK mà về sau xuất hiện khi hệ phục hồi **không phải lỗi**: có thể server commit rồi đánh mất response. Ngược lại, một request đã ACK thành công nhưng không thể tìm thấy sau recovery là trường hợp cần phân tích nghiêm túc.

### 1.1. Các đơn vị đo mất dữ liệu

- **Số bản ghi/operation:** bao nhiêu business intents đã ACK nhưng không còn?
- **Số byte:** tổng payload hoặc thay đổi logic bị mất; không nhầm với physical log bytes.
- **Khoảng thời gian:** khoảng cách giữa thời điểm crash/failover và commit gần nhất còn có thể phục hồi.
- **Dấu mốc log:** LSN, operation time, sequence number, stream offset hay version do hệ hỗ trợ.
- **Giá trị nghiệp vụ:** ví dụ 20 event xem trang khác hoàn toàn 1 payment confirmation bị mất.
- **Phạm vi:** một key, partition, shard, tenant, collection, cluster hay region.

Trong bài, **phạm vi mất** là tập các ý định hoặc thay đổi đã đạt mức cam kết được chọn nhưng không hiện diện trong trạng thái nguồn đã phục hồi đúng hợp đồng. Phải chọn mốc cam kết trước khi thử; không đổi định nghĩa ACK sau khi thấy kết quả.

## 2. RPO, RTO và độ mới đọc là ba câu hỏi khác nhau

**Recovery Point Objective (RPO)** mô tả mức mất dữ liệu tối đa chấp nhận được khi sự cố xảy ra, thường biểu diễn theo thời gian. **Recovery Time Objective (RTO)** là thời gian tối đa chấp nhận để phục hồi chức năng. **Read freshness** mô tả bản sao mà một lần đọc có thể thấy cũ đến đâu.

| Thuộc tính | Câu hỏi | Ví dụ mục tiêu giả định |
|---|---|---|
| RPO | Nếu region mất, còn tối đa bao nhiêu dữ liệu mới bị mất? | Không quá 30 giây dữ liệu đã commit |
| RTO | Mất bao lâu để có thể phục vụ lại? | Khôi phục checkout trong 10 phút |
| Staleness | Đọc ở replica phụ được phép cũ bao nhiêu? | Catalog cũ tối đa 60 giây khi khỏe |
| Durability | Write ACK sống qua lỗi nào? | Mất một node mà không mất write đã ACK |
| Availability | Trong lỗi, request nào còn hoàn tất? | Đọc catalog vẫn được, checkout có thể bị từ chối |

Không đồng nhất **replication lag 20 giây** với **RPO đã được chứng minh là 20 giây**. Lag là tín hiệu về một luồng sao chép tại thời điểm đo. RPO còn phụ thuộc bản sao được chọn khi failover, dữ liệu log có bền không, những partition không được quan sát, độ trễ báo metric và các thao tác đang in-flight.

### 2.1. RPO = 0 cần nói rõ phạm vi

Một lời hứa “RPO bằng 0” không thể được diễn giải là “không mất bất kỳ request nào đã đến mạng”. Nó phải nêu:

- **Mốc viết thành công:** ACK nào được tính?
- **Phạm vi dữ liệu:** một transaction/key/partition hay tất cả business events?
- **Loại sự cố:** crash process, mất node, mất AZ, mất region, mất toàn provider?
- **Giả định lỗi:** có bao nhiêu miền có thể mất đồng thời, mạng có partition không?
- **Trạng thái bên ngoài:** payment provider, queue, cache có nằm trong phạm vi không?
- **Quy trình recovery:** ai sẽ được chọn làm nguồn có thẩm quyền, bản ghi nào được replay?

Nếu toàn bộ các bản sao ACK nằm trong cùng một vùng địa lý và vùng đó mất vĩnh viễn, không thể từ số replica trong vùng suy ra RPO=0 với sự cố mất vùng đó.

## 3. Miền lỗi (failure domain) là gì?

**Miền lỗi** là tập thành phần có thể cùng bị ảnh hưởng bởi một nguyên nhân chung. Hai replica có PID khác nhau nhưng cùng host **không phải** hai miền lỗi máy độc lập. Hai máy khác nhau nhưng cùng AZ **không phải** hai miền lỗi AZ độc lập.

Một hệ có thể có các tầng:

~~~text
Ứng dụng / process
  └── Container / VM / node
       └── Host / rack / power/network segment
            └── Availability Zone / datacenter
                 └── Region
                      └── Cloud provider / account / control plane
~~~

Sơ đồ là một mô hình tham khảo: các miền lỗi thực tế **không luôn lồng hoàn toàn**. Chẳng hạn một dịch vụ quản lý khóa, DNS, mạng backbone, tài khoản, quyền vận hành hoặc pipeline triển khai có thể là phụ thuộc **dùng chung nhiều region**.

### 3.1. Những tình huống cần tách riêng

| Failure domain | Ví dụ sự cố | Điều cần xác minh |
|---|---|---|
| Process | Database process crash/restart | Journal, checkpoint, local recovery |
| Node/VM | Mất máy chủ sở hữu replica | Replica khác có dữ liệu và được phục vụ không? |
| Rack/power | Nhiều hosts cùng nguồn/mạng lỗi | Replicas có cùng rack không? |
| AZ/datacenter | Cả một vùng sẵn sàng không truy cập được | Quorum còn tồn tại ngoài AZ không? |
| Region | Mất một vùng địa lý/cloud region | Cross-region copy đã bền tới đâu? |
| Network partition | Nhóm nodes không trao đổi được nhưng vẫn chạy | Có split-brain hoặc ACK trên phía thiểu số không? |
| Control plane/credentials | Cùng tài khoản/khóa/cấu hình bị lỗi | Có bản sao mà không thể dùng/giải mã/khôi phục không? |
| Logical/operator error | DELETE nhầm, schema/script sai, corruption | Replica có thể sao chép lỗi; cần backup/PITR |

**Replica placement** là một câu trả lời hình học cụ thể: bản sao của cùng key/shard nằm trong những miền nào, và miền nào cùng phụ thuộc nguồn điện, mạng, control plane, encryption keys hoặc operational process.

## 4. Ba replica không đồng nghĩa chịu được mọi miền lỗi

Giả sử hệ có ba replica của partition `orders:p1`. Có ba cách đặt:

~~~text
Phương án A:
  Node-1, Node-2, Node-3 đều trong AZ-1

Phương án B:
  Node-1 ở AZ-1
  Node-2 ở AZ-2
  Node-3 ở AZ-3
  nhưng cả ba đều trong Region-R1

Phương án C:
  Node-1 ở Region-R1/AZ-1
  Node-2 ở Region-R1/AZ-2
  Node-3 ở Region-R2/AZ-1
~~~

Với phương án A, mất AZ-1 có thể làm mất cả ba bản sao, dù `replicationFactor=3`. Với B, có thể chịu mất một AZ tốt hơn nếu quorum/recovery protocol hợp lệ, nhưng **không** có bản sao ngoài Region-R1 nếu mất cả region. Với C, có bản sao ngoài region, nhưng việc **nó có đủ dữ liệu đã ACK để trở thành nguồn mới** còn phụ thuộc đồng bộ/commit protocol, không chỉ vị trí.

### 4.1. Ma trận miền lỗi cần xây cho từng dataset

| Dữ liệu | Owner/leader | Replicas | Miền lỗi độc lập | Bản sao ngoài region? |
|---|---|---|---|---|
| Order shard 0 | Node-A1 | A1, A2, A3 | AZ-1/2/3 trong R1 | Không |
| Inventory shard 7 | Node-B1 | B1, B2, B3 | AZ-1/2/3 trong R1 | Không |
| Audit log stream | Node-C1 | C1, C2, D1 | 2 AZ ở R1, 1 AZ ở R2 | Có |
| Backup/PITR | Service storage | Snapshot + change log | Tùy policy | Cần xác minh |

Bảng chỉ là mẫu minh họa. Không suy rằng “3 replicas cho toàn cluster” tức **mỗi partition** đều có 3 bản sao sẵn sàng trong các miền lỗi mong muốn. Cần khảo sát placement của **từng shard/partition** và replication progress theo shard.

## 5. Tại sao ACK, replicate, persist và visible khác nhau?

Một dòng thời gian khái niệm:

~~~text
T0: Client gửi write W1001.
T1: Primary/owner nhận và kiểm tra điều kiện.
T2: Thay đổi được áp vào memory và/hoặc log.
T3: Primary trả ACK theo policy.
T4: Replica B nhận hoặc áp thay đổi.
T5: Replica C nhận hoặc áp thay đổi.
T6: Các bản sao đạt durable sync/checkpoint theo engine.
T7: Cross-region replica/search/backup bắt kịp.
~~~

Thứ tự **chỉ để minh họa**, không phải thứ tự cố định của mọi storage engine. Một số policy chờ durable log/quorum trước ACK, một số ACK sớm, một số bước chạy song song.

Những mốc khác nhau:

- **Accepted:** server nhận request hoặc đưa vào queue.
- **Applied in memory:** trạng thái runtime đã thay đổi.
- **Committed/ACK:** write đạt điều kiện kết thúc được công bố và client thấy success.
- **Replicated:** bản sao khác đã nhận/áp log hoặc record.
- **Persisted/durable:** thông tin cần phục hồi sống qua loại crash được thiết kế.
- **Visible:** một read theo consistency mode cụ thể nhìn thấy bản mới.
- **Backed up:** dữ liệu có thể khôi phục bằng một snapshot/log độc lập theo retention.

Một bản sao nhìn thấy dữ liệu qua GET **không chứng minh** bản đó đã fsync log. Một snapshot chứa dữ liệu **không chứng minh** người dùng có thể đọc nó nhanh khi production gặp lỗi. Một ACK có ý nghĩa mạnh hay yếu phải được viết rõ trong test contract.

## 6. Replication đồng bộ và bất đồng bộ tạo cửa sổ mất khác nhau

**Synchronous replication** theo một contract có thể yêu cầu một số bản sao/miền xác nhận trước khi write trả thành công. **Asynchronous replication** có thể cho nguồn chủ ACK rồi chuyển dữ liệu sang bản sao sau.

Sơ đồ ý tưởng:

~~~text
Đồng bộ theo mốc cam kết:
  Client -> R1 owner -> R2 replica
         <- required ACKs
  Client <- Success

Bất đồng bộ:
  Client -> R1 owner
  Client <- Success
  ... sau đó ...
  R1 owner -> R2 replica
~~~

| Thuộc tính | Đồng bộ có ACK từ miền cần thiết | Bất đồng bộ |
|---|---|---|
| Latency ghi | Có thể tăng vì mạng và bản sao chậm | Thường có thể trả nhanh hơn |
| Mất source ngay sau ACK | Có thể giảm nguy cơ mất write ACK nếu replica ACK thực sự bền và độc lập | Có thể mất phần write chưa sang đích |
| Sẵn sàng khi link đứt | Có thể không commit nếu thiếu miền ACK bắt buộc | Có thể vẫn ghi ở source nếu policy cho phép |
| Khôi phục | Cần protocol chọn nguồn đúng | Đích có thể thiếu đoạn cuối |
| Phạm vi bảo đảm | Theo quorum/sync policy và loại lỗi | Theo tiến độ replica và tính bền của copy |

**Không dùng chữ “sync” một mình làm bằng chứng RPO=0.** Cần biết đồng bộ tới **RAM hay durable log**, số miền độc lập, ACK sau commit hay trước, leader election có tôn trọng committed index không, và những failure modes nào nằm trong hợp đồng.

## 7. Quorum quyết định điều gì?

Giả sử đơn giản một partition có `N=3` replicas, write phải được `W=2` bản sao công nhận, read tham chiếu `R=2` bản sao. Điều kiện giao tập:

\[
R+W>N
\]

cho thấy trong mô hình cùng tập replica và giả định phù hợp, tập read và tập write giao nhau. Nhưng **giao nhau không tự bảo đảm read linearizable, dữ liệu đã fsync, hay không thể mất khi region hỏng**.

Thực tế còn cần xem:

- Replica nào đã ACK, chúng nằm cùng AZ hay khác?
- ACK là nhận vào memory, commit log synced hay trạng thái khác?
- Dữ liệu viết đồng thời được so version/ordering thế nào?
- Dùng leader/consensus commit index hay multi-leader conflict resolution?
- Có transient owners, hinted handoff hoặc sloppy quorum không?
- Một replica có được bầu leader dù chưa có committed entry không?
- Đọc có chờ consistency level và source of truth phù hợp không?

### 7.1. Các ví dụ số lượng, không phải cam kết sản phẩm

| N | W | Trạng thái minh họa | Điểm cần lưu ý |
|---:|---:|---|---|
| 3 | 1 | Một bản sao có thể trả ACK | Mất đúng bản sao đó trước replication có thể mất write |
| 3 | 2 | Cần hai ACK | Chỉ có ý nghĩa chịu lỗi khi vị trí và durability ACK phù hợp |
| 3 | 3 | Cần cả ba ACK | Một replica không sẵn sàng có thể chặn ghi |
| 5 | 3 | Majority trong mô hình | Có thể chịu một số lỗi node, không tự chịu mất cả vùng chứa quorum |

Không giả định “W=2 nên dữ liệu sống qua mất một AZ” nếu cả hai ACK đến từ cùng AZ. Cũng không suy “W=3” là an toàn trước mất toàn region nếu cả ba ở trong region đó.

## 8. Khi mất miền lỗi, phải xác định tập bản sao còn dùng được

Đặt:

- `S(k)`: tập replicas chứa hoặc có khả năng giữ dữ liệu cho key/partition `k`.
- `F`: các replicas hoặc phụ thuộc bị mất do một failure domain cụ thể.
- `S(k)\F`: những replicas còn có thể phục vụ hoặc tham gia khôi phục.

Một câu hỏi cần kiểm tra:

\[
\text{Có nguồn nào trong } S(k)\setminus F
\text{ chứa mọi write đã được ACK theo contract không?}
\]

Đây là **điều kiện cần để lý giải dữ liệu còn**, nhưng chưa đủ nếu replicas còn lại không thể được bầu/khôi phục, keys không truy cập được, metadata bị mất hoặc copy bị corrupt.

Phải kiểm tra cho **mọi partition quan trọng**, không chỉ một collection có nhiều documents. Một cluster có 20 shards mà 19 shards còn dữ liệu, một shard mất các writes cuối, không thể kết luận RPO=0 cho toàn Order service.

## 9. RPO thực đo: dùng dấu mốc ghi thay vì nhìn dashboard

Giả sử một writer ghi tuần tự các events có IDs và sequence:

~~~json
{
  "partitionKey": "tenant:t01",
  "eventId": "evt-000042",
  "sequence": 42,
  "operation": "ORDER_CREATED",
  "createdAt": "2026-11-14T09:10:00Z"
}
~~~

Mỗi lần nhận database ACK, test harness lưu vào **ack ledger ở nơi độc lập với miền lỗi đang thử**. Sau crash/failover/restore, đọc lại dữ liệu từ nguồn đã được chỉ định là authoritative và đối soát với ledger.

Ví dụ:

~~~text
ACK ledger trước sự cố:
  evt-000001 ... evt-000100

Nguồn phục hồi:
  evt-000001 ... evt-000094

Cần điều tra:
  evt-000095 ... evt-000100
~~~

Kết luận ban đầu là **sáu events đã ACK không tìm thấy** theo đường đọc/khôi phục đang kiểm tra. Trước khi gọi đó là mất vĩnh viễn, phải xác minh chưa đọc nhầm replica stale, filter/index lag, quyền truy cập hay restore chưa hoàn tất.

### 9.1. Bốn tập để đối soát

- `A`: writes đã nhận ACK thành công theo client/harness.
- `C`: writes có bằng chứng commit theo log/metadata của nguồn.
- `D`: writes có trong dữ liệu authoritative sau recovery.
- `U`: writes gửi trước sự cố nhưng client chưa biết outcome.

Bước đối soát trọng tâm là `A - D`, đồng thời điều tra `C - D` và toàn bộ `U`. Tránh dùng `U` như “lost acknowledged writes”: chưa nhận ACK không đồng nghĩa chưa commit.

Số mất theo ACK ledger:

\[
L_{\mathrm{ack}}=|A\setminus D|
\]

Công thức mô tả **cách đếm**, không chứng minh vì sao dữ liệu thiếu. Nếu ACK ledger của chính harness nằm trong miền lỗi bị đánh sập, số liệu có thể sai; nó cũng cần durability độc lập, timestamps và khả năng tái đọc.

## 10. Khoảng thời gian mất khác số lượng bản ghi mất

Một ví dụ **giả định**:

~~~text
09:00:00  Snapshot/recovery point cuối có thể khôi phục
09:02:50  Một write đã ACK cuối cùng còn tại region dự phòng
09:03:00  Region nguồn hỏng
09:03:05  Failover hoàn tất về region dự phòng
~~~

Nếu mọi ACK sau `09:02:50` đều chỉ ở nguồn đã mất, **khoảng exposure đến lúc lỗi** là gần 10 giây. Nhưng cần cẩn thận:

- RPO đo từ **recovery point** được xác minh, không từ timestamp dashboard có độ trễ.
- Nếu workload không có write nào trong 10 giây đó, mất 0 record dù exposure theo thời gian là 10 giây.
- Nếu có 1.000 writes/giây trong khoảng đó, số records có thể lớn.
- Các partitions có lag khác nhau, nên điểm phục hồi toàn hệ có thể cũ hơn điểm của một key.
- Đồng hồ các máy khác nhau không đồng bộ có thể làm phép trừ timestamps sai.
- Transaction nhiều records có thể cần khôi phục nguyên nhóm, không chỉ xem record cuối.

Một ước lượng khối lượng trong điều kiện arrival rate gần như ổn định:

\[
\text{Writes phơi nhiễm} \approx \lambda_{\mathrm{writes}} \times \Delta t_{\mathrm{lag}}
\]

Ví dụ 200 writes/s và lag 5 s cho khoảng 1.000 writes phơi nhiễm **theo mô hình minh họa**. Đây không phải upper bound đáng tin trong burst traffic, không tính những write không ACK và không thay phép đo ledger thực tế.

## 11. Phân biệt “mất dữ liệu” với “đọc chưa thấy”

Sau failover, client truy vấn nhưng không thấy một record mới. Có ít nhất năm khả năng:

1. **Thực sự thiếu ở nguồn phục hồi** vì chưa được replicate hoặc log không bền.
2. **Replica đọc bị stale** dù record đã có trên authoritative replica.
3. **Search index/cache projection chưa bắt kịp** source.
4. **Khôi phục chưa hoàn tất**, WAL replay, compaction/index rebuild hoặc catch-up đang chạy.
5. **Truy vấn sai scope** (tenant, partition key, time range, deleted/TTL flags) hoặc quyền truy cập mới.

Thí nghiệm phải đọc bằng **đường được công bố để xác nhận authoritative state**, không chỉ GET qua CDN/search/secondary tùy chọn. Với hệ có nhiều leader/replicas, phải dùng consistency mode tương ứng và nêu giới hạn của nó.

Một version xuất hiện muộn trong cache không chứng minh “DB từng mất rồi tự tìm lại”; có thể đó chỉ là replication/index visibility lag.

## 12. Thiết kế sổ ACK độc lập để chứng minh kết quả

Một thí nghiệm nghiêm túc không được dựa duy nhất vào “application log nói success”, vì chính log đó có thể bị buffer hoặc mất theo cùng miền lỗi với database.

~~~mermaid
flowchart TD
    A["Generator tạo eventId và request"] --> B["Database primary/owner"]
    B --> C["ACK theo write policy"]
    C --> D["Harness ghi ACK ledger độc lập"]
    B --> E["Replica / standby / backup"]
    F["Fault injection: node/AZ/region"] --> B
    G["Sau lỗi: đọc nguồn phục hồi"] --> H["So sánh ACK ledger"]
    D --> H
    E --> G
~~~

Một dòng ACK ledger:

~~~json
{
  "runId": "drill-2026-11-14-01",
  "eventId": "evt-000084",
  "tenantId": "t01",
  "partition": "p7",
  "attempt": 1,
  "clientSendTime": "2026-11-14T10:00:01.050Z",
  "ackObservedTime": "2026-11-14T10:00:01.085Z",
  "ackKind": "WRITE_CONCERN_CONFIRMED",
  "commitToken": "source-specific-token",
  "payloadDigest": "sha256:<digest>"
}
~~~

Đây là schema minh họa, không phải API của một database. Chỉ đánh dấu `ACKED` sau khi driver nhận thành công đúng mức ACK đã thỏa thuận. Nếu request timeout, lưu trạng thái `UNKNOWN`, không tự đưa nó vào tập ACK.

### 12.1. Dấu mốc đáng tin có phạm vi riêng

Ưu tiên dấu mốc thứ tự được nguồn ghi có thẩm quyền cung cấp: commit index, operation time, LSN, log offset hoặc version của aggregate. Tuy nhiên:

- Sequence do nhiều clients tự sinh có thể không phản ánh **thứ tự commit toàn cục**.
- Timestamp client đo có thể lệch clock.
- Kafka offset của outbox event không tự là DB commit position.
- Nhiều shard có log riêng; không giả định có một LSN duy nhất toàn cluster.
- Một sequence gap có thể do request chưa ACK, không phải đã mất.
- Record được UPDATE/DELETE hợp lệ có thể không còn trong trạng thái cuối; cần immutable event ledger để phân biệt.

Để giảm nhầm lẫn, dataset thử nên có các **append-only records bất biến, ID duy nhất và payload digest**. Phải bảo vệ ACK ledger khỏi miền lỗi đang thử, đồng thời bảo đảm có thể đọc lại và đối soát nó.

## 13. Tăng dần cấp độ thử từ process tới AZ

Một tiến trình dừng đột ngột khác với toàn bộ ổ lưu trữ bị mất. Không lấy một lần restart thành công làm bằng chứng an toàn trước sự cố region.

| Thử nghiệm | Điều có thể kiểm chứng | Điều chưa chứng minh |
|---|---|---|
| Restart sạch | Startup và checkpoint bình thường | Crash đột ngột |
| Database process crash | Replay WAL/journal, election | Mất disk |
| Kill VM/node | Replica failover và dữ liệu ngoài node | Mất AZ |
| Node và storage không thể truy cập | Có copy độc lập ngoài node | Mất cả rack/AZ |
| AZ không truy cập được | Placement/quorum ngoài AZ | Mất cả region |
| Region không truy cập được | Cross-region standby và failover | Mất provider/control plane/keys |

Trong **process crash**, local WAL vẫn còn để replay. Trong **disk loss**, WAL trên chính disk đó có thể không còn. Trong **AZ outage**, nhiều nodes và phụ thuộc dùng chung có thể mất cùng lúc. Phải ghi rõ fault injection tạo loại lỗi nào, không suy từ tên test.

## 14. Quorum có còn sau khi một AZ mất?

Giả sử một nhóm consensus ba nodes, quorum majority là 2:

~~~text
AZ-1: Node A
AZ-2: Node B
AZ-3: Node C
Majority of 3 = 2
~~~

Nếu AZ-1 mất, B và C còn hai nodes, có thể giữ majority và elect leader mới **nếu giao thức và trạng thái log cho phép**. Nhưng nếu hai nodes A/B cùng nằm AZ-1, mất AZ-1 làm chỉ còn C và không có majority 2/3.

| Placement | Mất AZ có nhiều nodes nhất | Còn majority 2/3? |
|---|---|---|
| A, B, C trải 3 AZ | Còn 2 nodes | Có thể |
| A/B ở AZ-1, C ở AZ-2 | Còn 1 node | Không |
| A/B/C ở AZ-1 | Còn 0 | Không |
| A/B/C ở 3 AZ nhưng cùng region | Mất toàn region: còn 0 | Không |

**Còn quorum** chủ yếu nói đến khả năng protocol tiếp tục. Muốn chứng minh không mất ACKed writes còn phải xác minh **ACK durability, committed entries và election safety**.

### 14.1. Phải kiểm tra placement từng partition

Cluster có 20 shards có thể gồm 19 shards tốt và một shard thiếu replica đúng AZ hoặc đang rebalance. Nếu một shard mất dữ liệu, toàn Order service có thể không đạt mục tiêu RPO.

Đừng chỉ xem tổng healthy nodes. Cần replica placement, trạng thái recovery và commit progress **theo shard/partition/replica group**, đặc biệt với các partition nghiệp vụ quan trọng.

## 15. Mất region và cửa sổ của replication bất đồng bộ

Ví dụ source R1 replicate sang R2 theo kiểu bất đồng bộ:

~~~text
R1 primary                        R2 standby
ACK W101
ACK W102       --->               Applied through W100
ACK W103
REGION R1 LOST

Failover R2:
  Last applied = W100
~~~

Ba writes W101–W103 có nguy cơ thiếu ở R2. Cần đối soát bằng ACK ledger; một biểu đồ “lag = 3” chưa đủ xác nhận bộ writes nào bị thiếu.

Nếu yêu cầu RPO=0 trước **mất hẳn region nguồn**, cần một chính sách bảo đảm write ACK chỉ được đưa ra khi dữ liệu đã được lưu bền ở miền độc lập phù hợp và failover chọn được bản sao đã xác nhận committed history. Chính sách đó có thể tăng write latency, giảm availability khi link liên vùng đứt và tăng chi phí.

### 15.1. Lag khác nhau theo partition

~~~text
Partition P1: standby applied through seq=1000
Partition P2: standby applied through seq=980
Partition P3: standby applied through seq=1005
~~~

Nếu P2 đã ACK tới seq=1030 ở source, nó có exposure lớn hơn P1, dù dashboard lag trung bình trông đẹp. Cần **max/tail lag theo shard hoặc stream** chứ không chỉ trung bình của cluster.

## 16. Network partition khác region mất vĩnh viễn

Trong network partition, cả hai phía có thể vẫn chạy, chỉ không trao đổi message. Nếu failover quá sớm và không chặn owner cũ, có thể tạo **split-brain**:

~~~text
T0: R1 là owner của Order O42, version=7.
T1: Link R1-R2 chia cắt.
T2: R2 được promote mà không có fencing.
T3: R1 nhận update O42 -> version=8A.
T4: R2 nhận update O42 -> version=8B.
T5: Link phục hồi.
~~~

Không thể tự chữa mọi hậu quả bằng cách giữ version có timestamp mới hơn: 8A có thể đã trừ quota, 8B đã cập nhật payment. Cần **fencing/owner term/epoch/consensus** hoặc cơ chế conflict reconciliation đúng với domain.

### 16.1. Điều phải thử với owner cũ

- Old owner có tiếp tục commit sau khi mất quyền không?
- New owner có chỉ phục vụ sau khi đạt điều kiện log/commit safety không?
- Client retry có thể tra unknown outcome theo business ID không?
- Sau khi mạng hồi phục, committed histories có hội tụ đúng protocol không?
- DNS/routing thay đổi có đi kèm việc **chặn ghi từ owner cũ** không?

Một lease TTL tự hết không luôn đủ bảo vệ; worker cũ có thể tỉnh lại và ghi sau khi lease hết hạn. Fencing cần được nguồn có thẩm quyền kiểm tra.

## 17. Election và rollback: không phải mọi write đã xuất hiện là committed

Khi leader mất, một replica khác được bầu. Trong nhiều giao thức, entries chưa đạt commit/ACK level yêu cầu có thể không được giữ như committed history hoặc có thể bị rollback khi owner cũ trở lại.

| Tình huống | Cần xác minh |
|---|---|
| Request chưa ACK | Có thể commit hoặc chưa; outcome không rõ |
| Write ACK yếu hơn quorum commit | Có thể mất khi leader failover theo contract |
| Write ACK theo quorum commit | Kỳ vọng sống qua loại lỗi mà protocol bảo vệ |
| Log chỉ ghi trong RAM ở các node ACK | Durability phụ thuộc sync/replication policy |
| Old leader vẫn nhận write sau mất quyền | Rủi ro split-brain nếu không fenced |

Hỏi cụ thể:

1. Write đã đạt commit index/majority commit hay mới tồn tại trên primary?
2. Driver ACK chờ mốc nào?
3. Replica được bầu có phải chứa committed prefix không?
4. Những log entries chưa commit được xử lý thế nào sau election?
5. Recovery có replay/rollback những thay đổi nào?
6. Một client bị mất response có thể hỏi outcome bằng business intent ID không?

Một replica giữ bytes của W1001 không chứng minh W1001 thuộc **committed history** mà cụm mới phải giữ. Commit rules và election safety quan trọng hơn một lần đọc thấy bản ghi trên một node.

## 18. Replication không thay thế backup và PITR

Replication giữ nhiều bản sao trạng thái hiện hành, nhưng cũng có thể **lan truyền thay đổi sai**. Khi người vận hành xóa nhầm một collection, DELETE có thể được replicate tới tất cả nodes. Ba bản sao giống nhau ở trạng thái mất dữ liệu không giúp khôi phục dữ liệu trước khi xóa.

| Cơ chế | Bảo vệ điển hình | Không tự bảo vệ |
|---|---|---|
| Synchronous replication | Một số lỗi node/AZ theo ACK và placement | Xóa nhầm được replicate |
| Async standby | Mất nguồn theo RPO phụ thuộc lag | Các writes chưa chuyển tới standby |
| WAL/journal local | Process crash trước data-page flush | Mất toàn disk của node |
| Snapshot | Trạng thái tại mốc snapshot | Những writes sau mốc nếu không có log |
| Backup độc lập | Corruption/operator error theo retention | RTO thấp nếu chưa diễn tập |
| PITR | Khôi phục trong cửa sổ có log cần thiết | Ngoài retention/log bị mất |
| Business event log | Rebuild projection nếu event stream đầy đủ | Không tự bảo vệ dữ liệu nằm ngoài stream |

Cần hỏi:

- Backup có **nằm ngoài failure domain** cần bảo vệ không?
- Snapshot có transaction-consistent giữa shards không?
- PITR có đủ logs để khôi phục tới mốc mong muốn không?
- IAM, encryption keys, metadata và control plane có còn khả dụng sau sự cố không?
- Có restore drill chứng minh dữ liệu đọc đúng và ứng dụng hoạt động sau khi rebuild index không?
- Với lỗi xóa nhầm, có thể phục hồi tới trước lệnh xóa không và mất các ghi hợp lệ sau mốc đó bao nhiêu?

Một bản snapshot của shard A lúc 10:00 và shard B lúc 10:02 có thể phá invariant của một transaction nhiều shard. Không tự xem copy file trực tiếp trong lúc database chạy là backup nhất quán.

## 19. Phạm vi mất dữ liệu ở nhiều thành phần ứng dụng

Một ứng dụng có Order DB, Inventory DB, outbox, event broker, search projection và payment provider. Nếu region Order DB bị mất, mức mất của từng thành phần có thể khác nhau.

~~~mermaid
flowchart LR
    A["Order database"] --> B["Transactional outbox"]
    B --> C["Event broker"]
    C --> D["Search/Analytics projection"]
    A --> E["Inventory source"]
    A --> F["Payment provider"]
    G["Backup/PITR"] --> A
~~~

Những trường hợp:

1. Order đã commit nhưng outbox không cùng atomic transaction: event có thể thiếu.
2. Broker đã nhận event nhưng offset/log chưa bền theo contract: message có thể bị mất khi broker lỗi.
3. Search index thiếu document: có thể rebuild nếu source + change log đầy đủ.
4. Payment đã charge trong hệ ngoài, nhưng Order restore về bản trước charge: cần reconciliation theo paymentAttemptId.
5. Stock hold tồn tại nhưng record Reservation mapping bị mất: có thể không hoàn quota đúng.
6. Redis cache mất toàn bộ: có thể chấp nhận nếu mọi entry đều tái tạo từ nguồn chuẩn.

Không gộp RPO của tất cả thành phần thành một số duy nhất nếu business effects có yêu cầu khác nhau. Đặc biệt, **mất dữ liệu nguồn chuẩn** khác **mất bản dẫn xuất có thể rebuild**.

## 20. MongoDB: write concern và khả năng rollback

MongoDB replica set phân biệt **write concern**, **read concern**, **read preference** và durability của deployment. Các mức ACK khác nhau có phạm vi bảo đảm khác nhau.

Ví dụ:

~~~javascript
db.getCollection("orders").insertOne(
  {
    _id: "order-1001",
    tenantId: "t01",
    status: "CREATED",
    version: 1
  },
  { writeConcern: { w: "majority" } }
);
~~~

Không khẳng định mọi write `w:1` sống qua leader failover như một write đã được majority công nhận. Nhưng cũng không gộp majority thành “mọi node”, hoặc tự suy mọi journal sync nếu chưa xét phiên bản, cấu hình và tài liệu engine.

Thí nghiệm nên:

1. Xác định nodes/replicas của cùng shard nằm ở AZ nào.
2. Ghi immutable records có `runId, eventId, sequence, payloadDigest`.
3. Thu ACK ledger độc lập, phân biệt `w:1` và `w:"majority"` ở những test được phép.
4. Quan sát primary term, election, replication progress và log events.
5. Trong lab, gây process/node failure hoặc cô lập một AZ.
6. Đợi recovery theo protocol; đọc authoritative state.
7. Đối chiếu ACK ledger, ghi lại missing/unknown writes.
8. Kiểm tra rollback/recovery evidence, không chỉ một GET.

Một lần thử với `w:1` không mất record **không chứng minh** policy đó an toàn trước mọi node loss; follower có thể đã kịp sao chép trước sự cố.

## 21. Cassandra/ScyllaDB: RF và consistency level phải xét theo miền lỗi

Trong hệ họ Cassandra, cần xác định **replication factor**, replication strategy, datacenter/rack metadata và write/read consistency level của mỗi operation.

~~~text
RF = 3 trong DC1
Write CL = ONE hoặc LOCAL_QUORUM
Read CL  = ONE hoặc LOCAL_QUORUM
~~~

Các câu hỏi:

- Ba replicas của **mỗi partition** nằm ở các racks/AZ độc lập không?
- Khi một AZ mất, LOCAL_QUORUM còn đủ nodes không?
- Khi ACK ở ONE, node đó đã sync commit log theo policy chưa?
- Có hints/repair để đồng bộ sau khi node quay lại không?
- Replica vắng lâu và tombstones có làm bản ghi xóa xuất hiện lại nếu vận hành repair sai không?
- Khi nhiều datacenters, CL local có chờ DC khác không?
- Với LWT, serial consistency/quorum và phạm vi conditional update là gì?

**RF=3 không đồng nghĩa ba AZ** nếu replication strategy/placement không được cấu hình tương ứng. Read at ONE có thể thấy dữ liệu cũ từ một replica chưa bắt kịp; không đồng nhất “chưa thấy khi đọc” với “đã mất sau recovery”.

Với data model nhiều partitions, quorum của từng partition không biến các updates của Order và Inventory thành một transaction ACID chung.

## 22. DynamoDB: phân biệt vùng nguồn và global replication

DynamoDB là managed service: API cung cấp item/key, read consistency modes, transactional operations, backup/PITR và các chế độ multi-region, nhưng không công bố mọi file/replica layout nội bộ.

Một số điểm để đặt câu hỏi:

- Durability của **table trong một vùng** khác với mức copy ở vùng khác.
- Đường đọc strongly consistent/even­tual có phạm vi tùy table/index/feature.
- GSI có semantics indexing/replication riêng, không phải nguồn xác minh cuối khi dữ liệu phải mới nhất.
- Global Tables/cross-region replication có mode và hợp đồng riêng; không mặc định mọi write ACK đều đồng bộ bền ở mọi region.
- Backup/PITR tạo recovery points theo policy, khác active replica dùng để phục vụ.

Một kịch bản cần thử là write đã ACK trong R1, rồi R1 mất trước khi standby R2 nhận bản đó. Nếu configuration là **cross-region async**, đây có thể là exposure; phải kiểm tra theo mode cụ thể và nguồn dữ liệu sau failover. Nếu dịch vụ hỗ trợ hợp đồng đồng bộ/stronger mode, cần hiểu participant regions, ACK conditions và latency.

Không suy từ `PutItem`, `Query`, GSI hoặc tên “Global” rằng đã đạt RPO=0 trước mất vùng.

## 23. Redis: atomic không đồng nghĩa durable trước failover

Redis có các lệnh atomic trên server và những cơ chế persistence/replication như RDB, AOF tùy cấu hình. Nhưng:

- `INCR` atomic không tự bảo vệ trước mất node/storage.
- Một replica nhận write không nhất thiết fsync bền theo failure model.
- `WAIT` chờ một số replica xác nhận việc nhận write theo semantics Redis, **không tự biến toàn hệ thành consensus hoặc đảm bảo RPO=0**.
- Redis Cluster slot ownership, failover và các giới hạn multi-key operations phải được tính riêng.
- Eviction/TTL có thể làm cache key biến mất dù không có fault infrastructure.

Ví dụ quan sát:

~~~redis
INCR order-counter
WAIT 1 1000
INFO replication
INFO persistence
~~~

Nếu Redis chỉ là cache có thể rebuild, mất keys sau AZ outage có thể chấp nhận được; còn nếu Redis giữ quota/payments không có nguồn khác, phải chứng minh ACK, replication, persistence và recovery phù hợp business invariants.

## 24. Search, graph và analytics: phân biệt nguồn với projection

Một search/vector index hoặc graph projection có thể là bản dẫn xuất từ transaction source. Mất search shard không nhất thiết đồng nghĩa mất Product source, nhưng có thể làm search unavailable cho tới lúc rebuild.

Cần biết:

1. Ai là **source of truth** cho document, edge hoặc embedding?
2. Có snapshot/source hiện hành ở ngoài miền lỗi không?
3. Outbox/CDC/event log có thể replay mọi cập nhật sau snapshot không?
4. Index mapping, model version và transform logic có tái tạo được không?
5. Rebuild mất bao lâu và ảnh hưởng RTO như thế nào?
6. Có trường dữ liệu nào **chỉ tồn tại ở index** không?
7. Search stale có thể dẫn tới quyết định thanh toán hoặc cấp quota sai không?

Một index nhanh **không mặc định là backup đầy đủ**. Nếu có thể rebuild từ nguồn, cần tách mất dữ liệu logic khỏi thời gian không thể phục vụ search.

## 25. Bảng minh họa ACK và loại miền lỗi

| Mốc ACK được chọn | Process crash | Node/disk loss | AZ loss | Region loss |
|---|---|---|---|---|
| ACK ở RAM một node | Có thể mất nếu chưa log | Rủi ro nếu chưa copy | Phụ thuộc placement | Phụ thuộc copy ngoài region |
| ACK sau local durable log | Có thể replay local | Disk hỏng vẫn mất nếu không có copy | Cần bản sao ngoài AZ | Local log không bảo vệ mất region |
| ACK trên hai nodes cùng AZ | Có thể chịu process/node riêng | Có bản sao ngoài một node | Cả AZ vẫn là single failure domain | Không bảo vệ whole-region loss |
| ACK durable ở nhiều AZ cùng region | Có thể giảm AZ risk | Có bản sao độc lập | Cần commit/election safety | Chưa đủ cho whole-region loss |
| ACK durable ở region độc lập | Có thể đạt bảo đảm mạnh hơn theo protocol | Có copy ngoài node | Có copy ngoài AZ | Cần xác minh failover và committed history |
| Backup/PITR ngoài region | Restore theo recovery point | Có thể restore | Có thể restore | RPO phụ thuộc mốc backup/log |

“Có thể” là từ bắt buộc: **dữ liệu sống hay mất** không chỉ phụ thuộc số bản sao mà còn commit protocol, ACK durability, network partition, selection of recovery source và metadata/keys cần thiết.

## 26. Chuẩn bị thí nghiệm an toàn và tái lập được

Thử nghiệm phải chạy trong một môi trường **cô lập và được phép gây gián đoạn**, không tạo network partition, xóa storage hoặc ép failover production chỉ để “thử”.

Phải ghi:

- Version/edition, topology, số shard, RF và placement từng partition.
- Node/rack/AZ/region và những shared dependencies.
- Write concern/consistency level, read mode, journal/commit-log policy.
- Workload: arrival rate, payload, transaction size, hot/cold keys.
- Cách thu ACK ledger ở miền lỗi độc lập, độ bền của ledger.
- Cơ chế inject lỗi và cách xác nhận lỗi đã thực sự xảy ra.
- Protocol chọn authoritative state sau failover.
- RPO/RTO acceptance criteria **được đặt trước**.

Chuỗi test:

~~~text
Baseline -> Seed immutable data -> Record ACKs
         -> Inject controlled fault -> Observe reads/writes
         -> Recover/failover -> Read authoritative source
         -> Reconcile by business IDs -> Report outcome
~~~

Một thử nghiệm không mất record chỉ là **bằng chứng của lần thử đó**; không thay thế tài liệu về failure assumptions và replication protocol.

## 27. Ghi nhiều mốc thời gian, không dùng một timestamp

~~~text
T_send       Client phát write
T_ack        Driver nhận ACK theo policy
T_fault_cmd  Controller ra lệnh gây lỗi
T_fault_obs  Lỗi thực sự có hiệu lực
T_recover    Recovery/failover bắt đầu
T_usable     API authoritative phục vụ lại
T_verify     Hoàn tất đối soát ledger
~~~

Không giả định `T_fault_cmd = T_fault_obs`; cloud API, network rules, process termination và leader lease có độ trễ riêng. Client/DB clocks có thể không đồng bộ, nên khi xác định mốc **đã commit**, ưu tiên log positions/commit tokens và client ACK evidence.

Phân tách writes thành bốn nhóm:

1. Đã ACK trước lỗi theo mức cam kết yêu cầu.
2. Đang in-flight, outcome chưa biết.
3. Được hệ từ chối sau khi fault có hiệu lực.
4. Được retry/replay trong recovery.

Nếu gom nhóm 2 vào “mất acknowledged data”, số mất bị phóng đại; nếu chỉ đếm HTTP 200 sau failover, có thể bỏ lọt nhóm 1 đã thiếu ở standby.

## 28. Phân tích RPO bằng một tập ACK và một tập dữ liệu phục hồi

Để tránh tranh luận cảm tính, giả sử lab tạo 12 writes append-only:

~~~text
ACK ledger:
  W001 W002 W003 W004 W005 W006
  W007 W008 W009 W010 W011 W012

Sau failover, authoritative dataset:
  W001 W002 W003 W004 W005 W006
  W007 W008 W009

Mất khỏi dataset phục hồi:
  W010 W011 W012
~~~

Nếu toàn bộ W001–W012 đều đã ACK theo contract, ta ghi nhận:

- **Acknowledged writes missing:** 3.
- **Last contiguous ACKed sequence còn thấy:** W009.
- **Khoảng thời gian phơi nhiễm:** cần commit timestamps/positions tương ứng và mốc failure; chưa thể suy chỉ từ số sequence.
- **Nhóm UNKNOWN:** không có trong ví dụ, nhưng ở bài thực tế phải tách.
- **Business impact:** tùy ba writes là view events, stock movements hay Order confirmations.

Một phép thử **không thể xác nhận mất vĩnh viễn** khi chỉ đọc từ cache/search/replica eventual. Trước kết luận, phải đợi recovery/catch-up đúng quy trình và truy vấn nguồn theo consistency mode đã chọn.

## 29. Mẫu công cụ đối soát CSV đơn giản

Một bộ kiểm chứng có thể export hai file:

`ack.csv`:

~~~csv
run_id,event_id,partition,status,payload_digest
drill01,W001,p1,ACKED,hash001
drill01,W002,p1,ACKED,hash002
drill01,W003,p2,ACKED,hash003
drill01,W004,p2,UNKNOWN,hash004
~~~

`recovered.csv`:

~~~csv
run_id,event_id,partition,payload_digest
drill01,W001,p1,hash001
drill01,W003,p2,hash003
~~~

Đoạn Python sau **chỉ so sánh dữ liệu CSV đã thu thập**, không tự kết nối database, không giả lập network partition hay chứng minh tính bền của nguồn xuất dữ liệu:

~~~python
import csv
from collections import defaultdict


def rows_by_key(path):
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    result = {}
    for row in rows:
        key = (row["run_id"], row["event_id"])
        if key in result:
            raise ValueError(f"Duplicate ID in {path}: {key}")
        result[key] = row
    return result


ack = rows_by_key("ack.csv")
recovered = rows_by_key("recovered.csv")

missing = []
unknown = []
mismatch = []
counts = defaultdict(lambda: {
    "acknowledged": 0, "missing": 0, "unknown": 0
})

for key, recorded in ack.items():
    part = recorded["partition"]
    status = recorded["status"]
    if status == "UNKNOWN":
        unknown.append(key)
        counts[part]["unknown"] += 1
        continue
    if status != "ACKED":
        continue

    counts[part]["acknowledged"] += 1
    restored = recovered.get(key)

    if restored is None:
        missing.append(key)
        counts[part]["missing"] += 1
    elif (
        restored["partition"] != recorded["partition"]
        or restored["payload_digest"] != recorded["payload_digest"]
    ):
        mismatch.append(key)

print("Missing ACKed:", missing)
print("Unknown outcome:", unknown)
print("Digest/partition mismatch:", mismatch)
print("By partition:", dict(counts))
~~~

Kết quả mẫu:

~~~text
Missing ACKed: [('drill01', 'W002')]
Unknown outcome: [('drill01', 'W004')]
Digest/partition mismatch: []
By partition: {
  'p1': {'acknowledged': 2, 'missing': 1, 'unknown': 0},
  'p2': {'acknowledged': 1, 'missing': 0, 'unknown': 1}
}
~~~

**Giới hạn của công cụ:** dữ liệu có thể đã được delete/update hợp lệ, `eventId` có thể không đại diện một commit transaction, export có thể bỏ sót partition, và kết quả vẫn phụ thuộc read consistency của nguồn recovered. Ở production, cần đối soát bằng business intent/transaction history có thẩm quyền, kiểm tra duplicate IDs, nguyên nhân delete và metadata nguồn trước khi tuyên bố data loss.

### 29.1. Vì sao cần so digest ngoài IDs?

Một bản ghi ID W002 có thể tồn tại nhưng payload bị sai hoặc thuộc nhầm tenant. Khi đó kiểm tra chỉ “ID có xuất hiện” sẽ bỏ sót lỗi corruption/misrouting.

Cần đối chiếu tối thiểu:

- Run ID, tenant, partition/shard.
- Business/event ID.
- Payload digest hoặc những invariant fields.
- State/version cuối hoặc transaction outcome.
- Commit/ACK evidence và loại ACK.
- Với grouped transaction, tính toàn vẹn của **cả nhóm**.

Không đưa raw secrets, passwords hay thông tin thanh toán nhạy cảm vào ACK ledger của lab. Nếu hash payload, cần canonicalization phù hợp, tránh hai JSON cùng nghĩa nhưng thứ tự field khác làm digest khác.

## 30. Đo RPO thực tế từ recovery point, không từ timestamp được đoán

Giả sử một nguồn có write đã ACK gần nhất lúc 12:00:00, nhưng standby chỉ chứa trạng thái đã đồng bộ đến 11:59:42. Nếu nguồn mất ngay sau 12:00:00, **exposure time minh họa** là 18 giây.

\[
\Delta t = t_{\mathrm{source\ ACK\ cutoff}} -
           t_{\mathrm{last\ recoverable\ point}}
\]

Điều kiện để phép trừ có nghĩa:

1. Hai timestamps thể hiện cùng clock domain hoặc đã có cơ chế đồng bộ đủ tin cậy.
2. `last recoverable point` là **mốc có thể khôi phục được**, không chỉ metric “replica đã nhận packet”.
3. Source ACK cutoff được lấy theo đúng mức ghi cần bảo vệ.
4. Với nhiều shards, mốc phục hồi phải nhất quán nếu nghiệp vụ đòi transaction atomic nhiều shards.
5. Nếu không có write trong 18 giây, số writes mất có thể bằng 0.
6. Nếu nhiều người dùng gửi request cùng lúc, một mức lag nhỏ có thể tương ứng lượng nghiệp vụ lớn.

### 30.1. Không dùng average lag thay worst-case shard lag

Ví dụ ba partitions có observed lag:

| Partition | Lag minh họa | Business importance |
|---|---:|---|
| Search projections | 120 s | Có thể rebuild |
| Order shard P1 | 3 s | Quan trọng |
| Order shard P2 | 25 s | Quan trọng |

Một chỉ số average không phản ánh P2. Nếu mục tiêu Order RPO là 10 giây, cần cảnh báo P2 dù cluster average ở mức nhỏ. Chỉ tính các partitions liên quan và phân biệt **lag metric** với **khả năng phục hồi thực**.

## 31. Write throughput làm thay đổi rủi ro cùng một mức lag

Giả sử async replica trễ 5 giây và sự cố xảy ra:

| Workload giả định | Writes/giây | Writes có thể phơi nhiễm trong 5 giây |
|---|---:|---:|
| Catalog updates | 2 | Khoảng 10 |
| Order events | 100 | Khoảng 500 |
| Telemetry | 10.000 | Khoảng 50.000 |

Đây là ước lượng `rate × lag` để dự trù phạm vi, **không phải upper bound**. Traffic có burst, một write có thể chứa nhiều records, đồng hồ khác nhau và một số writes chưa ACK. Một event thanh toán quan trọng cũng không thể được đánh đồng với 1.000 telemetry events về mặt business impact.

Nên báo cáo song song:

- Lost/missing **ACKed intents count**.
- Missing **committed bytes/records** (nếu tính được).
- **Time-based RPO** thực đo.
- **Business severity** của nhóm missing.
- Tỷ lệ các phân vùng đã phục hồi và mức không chắc chắn.

## 32. RPO cho transaction nhóm và nhiều partitions

Giả sử Order creation transaction cập nhật:

~~~text
Order O1001        -> CREATED
Reservation R1001  -> HELD
StockPool SKU-A    -> available -= 2
Outbox E1001       -> ORDER_CREATED
~~~

Nếu nguồn đã **commit nguyên tử toàn bộ**, một bản restore có tính transaction-consistent phải trả trạng thái nhất quán theo protocol. Nếu từng thay đổi nằm ở hệ không có transaction chung, phải dùng Saga/outbox/ledger để phục hồi partial effects.

Sau lỗi, kiểm tra:

1. Order được tạo nhưng Reservation thiếu?
2. Stock giảm nhưng release/cancel workflow không có record để đối soát?
3. Outbox thiếu khiến event không được gửi?
4. Payment đã capture nhưng Order restore về PENDING?
5. Một phần dữ liệu hiện ở search nhưng source đã mất?

“Không thiếu một document ID riêng” chưa bảo đảm **invariant toàn workflow**. Với các transaction nhiều shard, mốc restore cần tôn trọng transaction boundaries; với Saga, cần khôi phục state machine và chạy compensation/reconciliation có điều kiện.

## 33. Khi dữ liệu nguồn mất nhưng downstream còn dấu vết

Đôi khi event broker hoặc payment provider còn giữ thông tin mà nguồn database đã mất. Có thể dùng để **đối soát** nhưng không tự coi là khôi phục an toàn mọi business fields.

Ví dụ:

~~~text
Order DB phục hồi đến 12:00.
Event broker còn OrderConfirmed tại 12:00:05.
Payment provider có successful charge lúc 12:00:06.
~~~

Một runbook nên:

- Xác định event/payment có IDs, amount, currency, tenant và signatures hợp lệ không.
- Đọc authoritative business state hiện tại.
- Kiểm tra event có thuộc commit hợp lệ hay là side effect chưa hoàn thành.
- Rebuild/reconcile theo idempotency key và state machine.
- Tránh replay mù gây duplicate charge hoặc double decrement.
- Ghi audit trail những khôi phục thủ công và lý do.

Không thể chỉ “apply lại mọi message sau thời điểm snapshot” nếu message có thể trùng/sai thứ tự hoặc nghiệp vụ đã bù trừ. Dữ liệu bên ngoài là **bằng chứng hữu ích**, nhưng cần logic nghiệp vụ xác minh.

## 34. Khôi phục sau lỗi phải có bước xác nhận quyền ghi

Rủi ro sau failover không chỉ là mất write cũ. **Write mới** có thể tiếp tục vào cluster sai hoặc vào owner cũ.

Một quy trình phục hồi có kiểm soát ở mức khái niệm:

1. Phát hiện failure domain và phạm vi data owners bị ảnh hưởng.
2. Xác định source/replicas còn sống cùng commit positions.
3. Bảo đảm old owners bị **fenced**, hoặc không còn quyền nhận ghi.
4. Chọn/promote nguồn có thẩm quyền theo protocol của database.
5. Khôi phục journal/log/replication tới mốc có thể xác minh.
6. Định tuyến clients tới owner mới, có retry/idempotency.
7. Đọc lại records từ authoritative path và đối soát ACK ledger.
8. Đánh giá business invariants, side effects ngoài database.
9. Mở lại writes khi các điều kiện safety/availability đã được đáp ứng.
10. Khi miền cũ quay lại, không tự đưa nó lên làm primary nếu log divergence chưa được xử lý theo protocol.

Đây là **runbook mẫu để thảo luận**, không phải lệnh thao tác trực tiếp trên sản phẩm. Hướng dẫn failover/restore phải dựa vào nhà cung cấp và phiên bản thực tế; có thể cần sự điều phối của operator và công cụ managed.

## 35. Quan sát và cảnh báo trước khi miền lỗi thật sự sập

Một bảng điều khiển nên có:

| Nhóm | Metric/câu hỏi |
|---|---|
| Placement | Replicas theo shard ở những AZ/regions nào? |
| Replica health | Số replicas khỏe/thiếu, replication stalled? |
| Commit progress | Leader term, committed positions, applied positions |
| Durability | Journal/commit-log sync lag, fsync failures |
| Async lag | Max/p95/p99 lag theo partition và vùng đích |
| Elections | Leader changes, rollbacks, unexpected failovers |
| Quorum | Các replica groups có đủ quorum khi mất một AZ không? |
| Recovery | Snapshot age, PITR window, backup restore test age |
| Data correctness | Missing ACKed events, digest mismatch, invariant violations |
| Business | Pending/unknown intents, stale payment reconciliations |
| RPO/RTO | RPO thực đo qua drill, time to usable authoritative API |
| Operational | Disk pressure, compaction, rebalance, config drift |

Một cảnh báo “region standby lag > 30 s” có thể cho biết **nguy cơ vượt RPO budget**, không nên mô tả nó như “đã mất 30 s dữ liệu” khi nguồn vẫn khỏe. Phân biệt **risk exposure** với **confirmed loss**.

### 35.1. Alert theo rủi ro hơn là đợi lỗi xảy ra

Nếu Order RPO mục tiêu gần 0 cho AZ outage, cần cảnh báo sớm khi một shard không còn placement/quorum độc lập ở nhiều AZ. Khi async regional standby có RPO budget 60 s, replication lag tăng tới 45 s có thể yêu cầu tăng mức chú ý, kiểm tra pipeline hoặc giảm tốc ghi, tùy policy. Đừng chỉ cảnh báo khi region đã mất.

## 36. Mẫu báo cáo thử lỗi

Một báo cáo không nên chỉ ghi “PASS: 3 replicas, failover OK”. Mẫu:

~~~yaml
experimentId: drill-order-region-loss-2026-11-14
environment: isolated-test
dataset: orders
failureDomain: region-R1
topology: "2 AZ in R1, standby in R2"
writeAckPolicy: "specified by tested deployment"
referenceSet: "durable external ACK ledger"
faultType: "controlled loss of R1 connectivity"
startOfFault: "observed by test controller"
recoverySource: "R2 standby"
acknowledgedOperations: 12000
unknownOutcomeOperations: 27
missingAcknowledgedOperations: 18
digestMismatches: 0
lastVerifiedRecoveryPoint: "source-specific commit token"
observedRpo: "derived from verified commit markers"
observedRto: "measured until authoritative API usable"
limitations:
  - "Partition P7 generated most missing writes"
  - "One test run; not a universal guarantee"
decision: "investigate / compare against predefined target"
~~~

Mọi giá trị số trong mẫu là **giả định**. Nếu chỉ có một lần diễn tập và chưa thể tạo đúng loại physical region outage, báo cáo phải nêu rõ limitation đó. Một mô phỏng network partition không chứng minh được khả năng sống qua mất hoàn toàn storage và khóa mã hóa trong region.

## 37. Các ngộ nhận cần tránh

| Ngộ nhận | Vì sao không đúng | Cách kiểm chứng |
|---|---|---|
| “RF=3 thì chịu được mất một region” | Ba replicas có thể đều trong cùng region | Placement theo từng shard |
| “Ba nodes nghĩa ba failure domains” | Có thể cùng rack/AZ/network | Bản đồ dependencies |
| “Replica nhận write tức đã bền” | Nhận vào RAM khác durable sync | ACK/log contract |
| “Quorum là bảo đảm không mất mọi dữ liệu” | Còn committed history, placement, election, sync | Protocol và fault drills |
| “R+W>N tự bảo đảm linearizability” | Giả định version/protocol có thể không thỏa | Consistency model thực tế |
| “ACK success nghĩa write đã vào backup” | Backup/PITR là pipeline khác | Restore point |
| “Có global replication là RPO=0 đa vùng” | Có thể async lag | Mode/ACK qua region |
| “Lag dashboard 5 giây = chắc chắn mất 5 giây” | Lag là exposure, không phải confirmed loss | ACK ledger vs recovered |
| “Mất process giống mất toàn disk” | Local WAL còn ở disk khi process crash | Test nhiều failure types |
| “Mất một AZ giống network partition” | Hai phía sống nhưng không liên lạc khác node bị mất hẳn | Cô lập vs destroy |
| “Node secondary đọc thiếu nghĩa đã mất data” | Có thể replica stale | Authoritative read sau catch-up |
| “Một lần failover không mất gì là bằng chứng tuyệt đối” | Timing có thể may mắn | Nhiều runs và protocol guarantee |
| “Mỗi shard có cùng RPO vì cluster healthy” | Lag/placement có thể lệch theo shard | Max lag và per-shard checks |
| “Writes chưa ACK chắc chắn không commit” | Response có thể mất sau commit | UNKNOWN outcome lookup |
| “Replica bầu leader mới là đủ” | Có thể cần committed log safety và fencing | Term/commit index |
| “Đổi DNS là chặn old leader” | Owner cũ vẫn có thể xử lý write | Fencing/term enforcement |
| “Replication bảo vệ DELETE nhầm” | DELETE có thể lan sang mọi replica | Backup/PITR độc lập |
| “Snapshot mọi shard cùng lúc theo clock là nhất quán” | Transaction có thể cắt qua mốc khác nhau | Consistent backup protocol |
| “Search index có đủ dữ liệu để rebuild Order” | Index có thể thiếu fields/history | Source/CDC coverage |
| “Nếu DB còn thì payment chắc đúng” | Provider nằm ngoài transaction DB | Reconciliation theo payment ID |
| “Có thêm replica luôn rẻ và nhanh hơn” | Quorum/coordination/storage/network tăng | SLO và cost benchmark |
| “RPO=0 nghĩa không mất bất kỳ request nào” | Chưa ACK/không commit khác đã commit | Chọn ACK boundary rõ |

## 38. Bài tập A — Ba cấu hình và một AZ mất

Xét cùng một dataset với ba phương án placement:

~~~text
A. Replica1, Replica2, Replica3 đều ở AZ-1.

B. Replica1 ở AZ-1,
   Replica2 ở AZ-2,
   Replica3 ở AZ-3.

C. Replica1 ở AZ-1/Region-R1,
   Replica2 ở AZ-2/Region-R1,
   Replica3 ở AZ-1/Region-R2.
~~~

Với từng phương án, trả lời:

1. Khi mất một node, còn bao nhiêu bản sao độc lập?
2. Khi mất AZ-1, còn bản sao nào?
3. Khi mất Region-R1, còn bản sao nào?
4. Với majority trong nhóm ba nodes, có còn quorum không?
5. Còn một replica có chứng minh write đã ACK bền không? Cần biết thêm điều gì?
6. Nếu write ACK đòi durable confirmation ở R2, tác động nào lên latency?
7. Nếu link R1–R2 partition, có thể tiếp tục ghi ở R1 với cùng contract không?
8. Recovery nên chọn nguồn nào và cần fencing thế nào?

**Chú ý:** C không tự có RPO=0 cho region loss chỉ vì chứa một node ngoài region; nếu nó không nhận những writes đã ACK, dữ liệu cuối vẫn có thể thiếu.

## 39. Bài tập B — Tính khoảng phơi nhiễm dữ liệu

Một ứng dụng ghi event vào R1 và async replicate tới R2. Các mốc giả định:

~~~text
12:00:00.000  Standby R2 xác minh đến event 900
12:00:04.000  Standby R2 xác minh đến event 940
12:00:05.000  Region R1 gặp lỗi
12:00:05.300  Failover chọn R2
~~~

ACK ledger của client trước sự cố:

~~~text
ACK event 901 ... 980
UNKNOWN outcome event 981 ... 985
~~~

Hãy:

1. Xác định tập ACKed events có thể thiếu khi R2 chỉ chứa tới 940.
2. Đếm số ACKed events cần đối soát khi R2 phục hồi.
3. Xác định vì sao không được tính 981–985 là “mất dữ liệu đã ACK”.
4. Nếu một số IDs trong 941–980 được viết lại hợp lệ hoặc duplicate do retry, phải đối soát theo tiêu chí nào?
5. Tính time-based exposure từ các mốc có căn cứ; giải thích vì sao cần commit timestamps/positions chứ không chỉ event IDs.
6. Nếu mục tiêu RPO là 1 giây, một lag khoảng 1 giây có đủ **chứng minh** đã đạt không?
7. Một shard P2 chưa đồng bộ tới 920 có làm kết luận khác không?
8. Hãy lập báo cáo missing ACK count, unknown count, last recoverable point và limitation.

## 40. Bài tập C — Khác biệt giữa mất data và dữ liệu chưa nhìn thấy

Sau failover, người dùng tìm Order O1001 trên ba đường:

~~~text
GET /orders/O1001            -> FOUND
GET /search?q=O1001          -> NOT_FOUND
GET /orders-replica/O1001    -> NOT_FOUND
~~~

Câu hỏi:

1. Có thể khẳng định Order O1001 đã mất không?
2. Đường đọc nào là nguồn có thẩm quyền?
3. Nếu search/index replication lag 20 giây, điều đó có vi phạm Order RPO không?
4. Nếu Order có nhưng OutboxEvent mất, sẽ xuất hiện hệ quả gì?
5. Nếu payment provider có charge nhưng Order mất ở source, cần kiểm tra gì?
6. Một test chỉ truy vấn search API có phù hợp để chứng minh RPO của Order DB không?
7. Cần thu thêm commit token, source digest hoặc broker event ID nào?
8. Sau khi authoritative state đã được đối soát, cần kiểm tra projection hội tụ ra sao?

## 41. Bài tập D — Thiết kế một disaster recovery drill

Tưởng tượng hệ NoSQL chứa ba nhóm dữ liệu:

| Loại | Mục tiêu kinh doanh giả định |
|---|---|
| Catalog | Chấp nhận mất 10 phút cập nhật nếu có thể đồng bộ lại |
| Order/Reservation | Không muốn mất những writes đã ACK khi mất một AZ |
| Payment reconciliation log | Cần đối soát mọi giao dịch đã thu tiền |
 
Hãy xây một kế hoạch gồm:

1. Mô tả failure domain cần thử (process, node, AZ, region, operator error).
2. Định nghĩa ACK policy và write/read consistency của từng loại dữ liệu.
3. Vẽ bản đồ replicas theo shard và AZ/region.
4. Chọn RPO, RTO theo từng dataset.
5. Thiết kế durable ACK ledger đặt ngoài miền lỗi đang thử.
6. Chọn workload immutable và đảm bảo IDs/payload digests duy nhất.
7. Xác định phép thử có thể gây gián đoạn trong lab và cách rollback.
8. Mô tả source nào được gọi là authoritative sau failover.
9. Liệt kê các bước kiểm tra `ACKED - RECOVERED` và UNKNOWN outcomes.
10. Nêu biện pháp tránh split-brain khi old owner trở lại.
11. Xác định cách phục hồi cache/search và outbox.
12. Lập mẫu báo cáo RPO/RTO thực đo, kết quả và giới hạn.

Sau bài tập, tự đánh giá liệu một câu “đã cấu hình RF=3” có đủ thay thế toàn bộ kế hoạch trên không.

## 42. Câu hỏi tự kiểm tra

1. Miền lỗi là gì? Ba replica trên ba VM cùng AZ có độc lập trước AZ outage không?
2. ACKed, applied, journaled, visible và backed up khác nhau thế nào?
3. Vì sao process crash không tương đương mất cả disk?
4. RPO khác RTO và read freshness như thế nào?
5. Khi nào có thể khẳng định RPO=0, theo phạm vi nào?
6. Vì sao RF=3 không tự bảo vệ mất region?
7. Điều kiện quorum còn sống có tự chứng minh mọi ACKed write bền không?
8. Vì sao `R+W>N` chưa đủ cho kết luận linearizable trong mọi engine?
9. Synchronous cross-region ACK có thể tăng latency và giảm availability ra sao?
10. Async replica đang lag 10 giây có nghĩa đã mất 10 giây dữ liệu chưa?
11. Vì sao phải có ACK ledger độc lập với miền lỗi thử nghiệm?
12. Ghi sequence từ nhiều clients có phản ánh commit order toàn cục không?
13. Tập UNKNOWN cần xử lý khác ACKED như thế nào?
14. Trong failover, read từ secondary stale có thể khiến kết luận data loss sai ra sao?
15. Owner cũ chưa bị fenced tạo split-brain thế nào?
16. Vì sao một bản sao chứa log entry chưa chứng minh entry đó đã commit?
17. Làm sao xác minh replica placement theo từng shard?
18. Replication và PITR bảo vệ lỗi khác nhau nào?
19. Vì sao backup nhiều shards cần mốc transaction-consistent?
20. Khi restore Order về mốc cũ nhưng provider đã charge, phải đối soát như thế nào?
21. MongoDB `w:1` và `w:"majority"` cần kiểm thử ở những loại lỗi nào?
22. Cassandra RF/CL/replica placement ảnh hưởng khả năng đọc-ghi sau mất AZ ra sao?
23. DynamoDB cross-region replication có thể có những hợp đồng khác nhau vì sao?
24. Vì sao Redis `WAIT` không tự là cam kết RPO=0?
25. Khi search projection bị mất, có thể rebuild từ nguồn nào?
26. RPO count, time exposure và business impact cần báo cáo đồng thời ra sao?
27. Có nên dùng average replication lag để đại diện mọi partition không?
28. Chỉ số nào giúp cảnh báo **nguy cơ vượt RPO** trước khi lỗi thật sự xảy ra?
29. Một lần diễn tập thành công có chứng minh mọi future failures đều không mất dữ liệu không?
30. Tại sao phải định nghĩa pass/fail criteria trước khi fault injection?

## 43. Tổng kết: bảo vệ dữ liệu phải được chứng minh theo miền lỗi

Trong NoSQL, **sao chép không chỉ là số bản sao**, và **quorum không chỉ là một phép đếm ACK**. Khả năng giữ dữ liệu sau khi node, AZ hoặc region gặp sự cố phụ thuộc vào **vị trí và sự độc lập của replicas, mốc commit/ACK thực sự, độ bền log, điều kiện election/fencing, tiến độ replication, cách chọn nguồn khôi phục và backup/PITR**.

Phương pháp thiết kế và kiểm chứng có thể gói lại thành một chuỗi:

~~~text
1. Xác định business data và source of truth.
2. Phân loại failure domain cần chịu được.
3. Chọn RPO/RTO và mốc ACK cụ thể.
4. Vẽ placement theo mỗi partition/shard.
5. Xác định quorum, durable log và replication semantics.
6. Ghi immutable IDs + external ACK ledger.
7. Gây lỗi có kiểm soát trong môi trường thử.
8. Khôi phục theo protocol, fence old owner.
9. Đối soát ACKed writes với authoritative recovered state.
10. Báo cáo missing, unknown, lag, RPO/RTO và business impact.
11. Diễn tập lại sau khi đổi topology/config/phiên bản.
~~~

Kết luận không nên chỉ là “cluster đã failover thành công”. Một kết luận hữu ích phải nêu: **“Với failure domain X, write acknowledgment Y, placement Z và quy trình phục hồi R, tất cả những event IDs đã ACK trong thử nghiệm có còn hay không; nếu thiếu thì thiếu những gì, trong bao lâu, vì sao, và các giả định nào giới hạn kết quả.”**

Chính cách đặt câu hỏi và đối soát có bằng chứng như vậy mới cho phép chuyển từ **niềm tin rằng replication sẽ bảo vệ dữ liệu** sang **khả năng kiểm chứng phạm vi dữ liệu thực sự có thể mất khi một miền lỗi gặp sự cố**.







