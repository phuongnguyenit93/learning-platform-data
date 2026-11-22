# Mục tiêu phân mảnh dữ liệu và khác biệt với tạo bản sao

Một database NoSQL ban đầu thường chạy tốt trên một máy: dữ liệu còn ít, số lượng request nhỏ và toàn bộ tập dữ liệu có thể được truy cập qua một node. Khi sản phẩm tăng trưởng, các giới hạn bắt đầu xuất hiện: dung lượng đĩa và RAM không còn đủ, CPU bị bão hòa, một máy không xử lý kịp số lượng ghi hoặc một số tenant tạo tải quá lớn. Lúc này, hai kỹ thuật thường được nhắc tới là **phân mảnh dữ liệu** (*sharding/partitioning*) và **tạo bản sao** (*replication*).

Hai kỹ thuật đều sử dụng nhiều node nhưng giải quyết **hai nhóm bài toán khác nhau**:

- **Phân mảnh:** Chia một tập dữ liệu logic thành những phần khác nhau và đặt chúng trên các node/nhóm node khác nhau. Mục tiêu chính là **phân phối dung lượng, tải tính toán và lưu lượng truy cập**, giúp hệ mở rộng theo chiều ngang.
- **Tạo bản sao:** Duy trì nhiều bản của **cùng một phần dữ liệu**, thường trên những node hoặc vùng lỗi khác nhau. Mục tiêu chính là **khả năng chịu lỗi, độ sẵn sàng khi node hỏng, khả năng khôi phục** và đôi khi tăng năng lực đọc theo chính sách consistency.

Phân mảnh **không tự tạo dự phòng** cho dữ liệu; tạo bản sao **không mặc nhiên chia nhỏ tập dữ liệu để giảm dung lượng mỗi bản**. Một hệ thống production có thể, và thường cần, **cả hai**: mỗi shard quản lý một phần dữ liệu, rồi phần đó được nhân bản thành nhiều replica.

Bài học sẽ làm rõ mục tiêu, kiến trúc, định tuyến truy vấn, thiết kế khóa phân mảnh, chi phí vận hành và cách nhận biết trong các hệ NoSQL phổ biến. Các số liệu trong ví dụ được dùng để minh họa phép tính, không phải benchmark đã thực hiện.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **shard/partition** và **replica** bằng cùng một ví dụ dữ liệu.
2. Phân biệt mở rộng dung lượng/ghi/CPU nhờ phân mảnh với tăng dự phòng hoặc năng lực đọc nhờ replication.
3. Vẽ sơ đồ một cluster vừa có nhiều shard vừa có nhiều replica cho mỗi shard.
4. Hiểu **logical partition**, **physical node**, **replica**, **routing** và vì sao không được mặc định “một partition bằng một server”.
5. So sánh khóa phân mảnh theo **range**, **hash**, **tenant**, **directory** và các cách kết hợp.
6. Giải thích **targeted query** khác **scatter–gather** và chi phí của truy vấn xuyên shard.
7. Phát hiện **data skew**, **hot key/hot shard**, **monotonic key** và giới hạn của một cluster có nhiều máy.
8. Nêu các bước chính của **rebalancing/resharding**, cũng như rủi ro khi dịch chuyển dữ liệu đang có ghi.
9. Nhận diện cách các khái niệm xuất hiện trong MongoDB, Cassandra/ScyllaDB, DynamoDB, Elasticsearch/OpenSearch và Redis Cluster.
10. Đề xuất thiết kế cho bài toán đa tenant, đồng thời giữ đúng yêu cầu nhất quán, transaction, backup và độ trễ.

## 2. Bài toán xuyên suốt: dữ liệu đơn hàng tăng trưởng

Giả sử một ứng dụng thương mại lưu các document:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "shopId": "shop-12",
  "status": "PAID",
  "createdAt": "2026-11-14T09:30:00Z",
  "totalVnd": 1250000
}
~~~

Ban đầu, mọi Order nằm trên một database node:

~~~text
Client / API
     |
     v
+------------------------------+
| Node A                       |
| 12.000.000 Order             |
| Indexes, RAM, CPU, disk, I/O |
+------------------------------+
~~~

Sau khi mở rộng hệ thống, có thể đặt ra những mục tiêu khác nhau:

| Vấn đề | Câu hỏi thiết kế | Hướng kỹ thuật cần xem |
| --- | --- | --- |
| Một node không đủ dung lượng | Làm sao chia tập Order để mỗi máy chỉ giữ một phần? | **Sharding** |
| Một node không đủ throughput ghi | Làm sao phân phối write tới nhiều owner? | **Sharding**, nếu workload phân bố được |
| Một node hỏng gây mất truy cập | Có node khác giữ cùng dữ liệu để tiếp tục không? | **Replication/failover** |
| Mất ổ đĩa có thể mất dữ liệu | Có bản sao và bản sao lưu đáng tin cậy không? | **Replication + backup/durability** |
| Nhiều client chỉ đọc danh mục | Có thể phục vụ read từ nhiều bản sao phù hợp consistency? | **Read replicas/cache**, có thể kết hợp sharding |
| Một tenant lớn gây nghẽn | Có cách trải tải của tenant đó lên nhiều owner? | **Shard-key design/bucketing** |
| Người dùng nhiều vùng địa lý | Có thể giảm round trip và đặt dữ liệu gần người dùng? | **Placement + routing + replication/sharding**, tùy hợp đồng |

**Một mục tiêu không đồng nghĩa một cấu hình duy nhất.** Trước khi thêm server, hãy xác định nút thắt là dung lượng, ghi, đọc, latency mạng, hay khả năng chịu lỗi.

## 3. Phân mảnh dữ liệu là gì?

**Phân mảnh ngang** (*horizontal partitioning/sharding*) chia các **bản ghi hoặc document** trong một tập dữ liệu logic thành các nhóm không trùng nhau theo một quy tắc phân phối.

Ví dụ 12 triệu Order được chia thành bốn phần:

~~~text
                 Orders (logical collection)
                         12.000.000
                              |
              +---------------+---------------+
              |               |               |
           Shard 0         Shard 1         Shard 2       Shard 3
          3 triệu          3 triệu        3 triệu       3 triệu
              |               |               |             |
           Node A          Node B          Node C        Node D
~~~

Đây là **phân bố lý tưởng để minh họa**. Thực tế số bản ghi, dung lượng và tải ở từng shard có thể rất khác nhau.

Mỗi Order có **một shard sở hữu dữ liệu logic** theo chính sách phân mảnh; điều này không có nghĩa nó chỉ tồn tại ở một physical node, vì shard ấy có thể được **nhân bản**.

### 3.1. Mục tiêu của phân mảnh

Phân mảnh thường nhằm:

- **Scale-out dung lượng:** Tập dữ liệu lớn hơn sức chứa hợp lý của một máy.
- **Scale-out năng lực ghi:** Các request tới những shard khác nhau có thể được xử lý trên nhiều nhóm tài nguyên độc lập.
- **Phân phối CPU/I/O/RAM:** Một node không phải xử lý toàn bộ dữ liệu và truy vấn.
- **Cô lập một phần tải:** Tùy thiết kế, giảm tác động giữa những nhóm tenant hoặc workload.
- **Hỗ trợ placement:** Đặt shard gần khu vực truy cập hoặc đáp ứng yêu cầu nơi lưu trữ dữ liệu.
- **Mở rộng theo tăng trưởng:** Thêm tài nguyên và dịch chuyển một phần dữ liệu thay vì thay toàn bộ hệ bằng một máy lớn hơn.

### 3.2. Những điều phân mảnh không tự bảo đảm

Thêm shard **không mặc nhiên**:

- Làm mọi truy vấn nhanh gấp số shard.
- Làm một hot key có thể ghi đồng thời vô hạn.
- Bảo vệ dữ liệu khi node chứa shard chết.
- Cung cấp linearizability, transaction xuyên shard hoặc uniqueness toàn cục.
- Xóa chi phí routing, network và merge kết quả.
- Giải quyết câu truy vấn thiếu shard key.

Một truy vấn phải fan-out đến tất cả shard có thể **chậm hơn** truy vấn chạy trên một node, nếu dữ liệu còn nhỏ và chi phí network/coordination lớn.

## 4. Tạo bản sao là gì?

**Replication** lưu nhiều bản của **cùng một đơn vị dữ liệu** trên nhiều node/failure domain.

Ví dụ cả 12 triệu Order chưa được phân mảnh, nhưng có ba bản:

~~~text
                   Orders (logical dataset)
                        12 triệu
                           |
            +--------------+---------------+
            |              |               |
         Replica A      Replica B       Replica C
         12 triệu       12 triệu        12 triệu
          Node A         Node B          Node C
~~~

Một replica có thể được dùng để:

- Tiếp tục phục vụ khi node khác chết, theo giao thức **election/failover/quorum**.
- Tăng durability khi dữ liệu được lưu ở các failure domain khác nhau.
- Phục vụ thêm read khi việc đọc từ replica phù hợp với consistency và freshness được yêu cầu.
- Giảm một số round trip bằng replica gần vùng truy cập, với những đánh đổi về đồng bộ.
- Cung cấp dữ liệu để thay node hoặc tái tạo bản sao sau sự cố.

### 4.1. Replication không đồng nghĩa scale-out ghi

Nếu một hệ có **một leader** cho tập dữ liệu:

~~~text
Client writes -> Leader
                 | \
                 v  v
              Replica B, C
~~~

Tất cả write logic vẫn phải đi qua leader/authority hoặc giao thức đồng thuận cho cùng dữ liệu. Thêm replica có thể **tăng chi phí ghi** do mỗi mutation phải được nhân bản, chứ không có nghĩa throughput ghi của một hot key tăng gấp ba.

Một số hệ nhận ghi nhiều nơi, nhưng khi đó xuất hiện bài toán **concurrent writes, reconciliation, consistency và conflict resolution**. Không được suy rằng multi-writer replication xóa được mọi giới hạn.

### 4.2. Replication không thay backup

Một lệnh xóa nhầm Order có thể được **nhân bản chính xác** sang mọi replica. Một lỗi ứng dụng, corruption logic hoặc ransomware cũng có thể ảnh hưởng nhiều bản sao đang hoạt động.

Vì thế:

> **Replica dùng để phục vụ/khôi phục hoạt động sau sự cố phần cứng hoặc node; backup/snapshot có chính sách lưu giữ độc lập dùng để phục hồi dữ liệu từ một thời điểm cần thiết.**

Hệ thống quan trọng thường cần **replication, backup, kiểm tra restore và cơ chế bảo vệ quyền truy cập** đồng thời.

## 5. Một bảng so sánh phân mảnh và nhân bản

| Khía cạnh | **Phân mảnh (sharding)** | **Tạo bản sao (replication)** |
| --- | --- | --- |
| Cách phân phối | Các phần dữ liệu logic **khác nhau** | Nhiều bản của **cùng một phần dữ liệu** |
| Mục tiêu chính | Scale-out dung lượng/tải/ghi | Chịu lỗi, failover, durability; đôi khi read scale |
| Dữ liệu trên một node | Thường chỉ một tập con | Có thể là cùng tập con với các replica khác |
| Khi thêm node | Có thể đặt/chuyển shards sang node mới | Có thể tạo thêm replica, tùy replica policy |
| Tác động dung lượng | Trải dữ liệu logic ra nhiều máy | Tăng tổng byte lưu do các bản sao |
| Tác động write | Có thể phân phối write sang nhiều owners | Có thể tốn thêm replication work |
| Tác động read | Targeted query có ít dữ liệu hơn | Read replica có thể chia tải nếu policy cho phép |
| Node hỏng | Nếu shard không có replica, phần dữ liệu đó có thể không truy cập được | Replica khác có thể tiếp quản theo cơ chế hệ |
| Rủi ro chính | Shard skew, hot key, fan-out, rebalancing | Lag, failover, split-brain, conflict, cost |
| Bài toán định tuyến | Xác định **shard owner** theo key/map | Chọn **replica** nào có thể phục vụ read/write |
| Giao dịch | Có thể trải qua nhiều shard | Có thể cần quorum/leader cho cùng shard |
| Ví dụ trực quan | Chia sách thành nhiều kệ, mỗi kệ giữ chương khác nhau | In thêm bản sao của từng chương |

**Câu dễ nhớ:** Sharding trả lời **“dữ liệu nào ở đâu?”**; replication trả lời **“có bao nhiêu bản của phần dữ liệu ấy và ai được phép phục vụ?”**

## 6. Sơ đồ kết hợp: bốn shard, mỗi shard ba replica

Một kiến trúc phổ biến là **replicate từng shard**:

~~~text
                 Logical Orders dataset
                           |
           +---------------+---------------+---------------+
           |               |               |               |
         Shard 0         Shard 1         Shard 2         Shard 3
         Orders A        Orders B        Orders C        Orders D
           |               |               |               |
       +---+---+       +---+---+       +---+---+       +---+---+
       |   |   |       |   |   |       |   |   |       |   |   |
       P   R   R       P   R   R       P   R   R       P   R   R

       P = primary/owner cho shard, nếu engine dùng leader.
       R = replica của cùng shard.
~~~

Không phải engine nào cũng có một primary/follower model như hình; một số dùng **peer replication và quorum**. Ý tưởng chung vẫn là: **bốn phần dữ liệu logic khác nhau, mỗi phần có ba bản vật lý**.

### 6.1. Đếm đúng số shard và replica

Ví dụ:

~~~text
Logical shards = 4
Replication factor (RF) = 3
Replica placements = 4 × 3 = 12
~~~

**12 replica placements không có nghĩa bắt buộc 12 máy.** Một physical node có thể chứa nhiều replica của những shard khác nhau, tùy sản phẩm và chiến lược placement. Nhưng tránh đặt **nhiều bản của cùng shard trên cùng một failure domain** nếu mục tiêu là chịu lỗi node/AZ.

### 6.2. Hai bước của một request

Khi ứng dụng đọc `Order O900`:

1. **Xác định shard owner** dựa trên shard key hoặc directory.
2. **Chọn replica** trong nhóm của shard đó theo consistency/read preference/health.

Khi ghi:

1. Xác định shard sở hữu Order.
2. Gửi mutation tới authority/quorum phù hợp.
3. Xác nhận thành công theo ack/write concern đã hứa.
4. Replication/catch-up được thực hiện theo giao thức.

Một hệ có thể có routing riêng, proxy/gateway hoặc client driver đảm nhận nhiều bước. Không có quy tắc duy nhất bắt buộc ứng dụng tự tính mọi shard.

## 7. Dung lượng: tính theo dữ liệu logic và số bản sao

Giả sử:

~~~text
Số Order                         = 12.000.000
Dung lượng trung bình / Order    = 2 KB (decimal, giả định)
Tổng document data               = 24 GB (decimal)
Dung lượng index ước tính        = 50% document data
Tổng data + index logic         = 36 GB
Số shard                         = 4
Replica factor                   = 3
~~~

Nếu phân phối **đều theo byte**:

\[
\text{Storage logic mỗi shard} = \frac{36}{4}=9\ \text{GB}
\]

Nếu mỗi shard có ba bản vật lý đầy đủ:

\[
\text{Tổng dung lượng bản sao} \approx 36\times 3=108\ \text{GB}
\]

Mỗi nhóm shard có khoảng:

~~~text
Primary/logical data+index per shard = 9 GB
Total copies of that shard at RF=3 = 27 GB
All four shards with replicas      = 108 GB
~~~

Các con số **không bao gồm** WAL/journal, compaction, metadata, snapshots, tombstones, growth headroom và chi phí khác; cũng chưa tính replica có thể dùng encoding/compression khác nhau.

### 7.1. So ba kiến trúc

| Kiến trúc | Phân bố dữ liệu | Dung lượng tổng ước tính | Dung lượng trên mỗi bản |
| --- | --- | ---: | ---: |
| Một node, một bản | Toàn bộ dataset trên một máy | 36 GB | 36 GB |
| Một shard, RF=3 | Ba bản của toàn bộ dataset | 108 GB | 36 GB |
| Bốn shard, RF=1 | Bốn tập con, không replica | 36 GB | ~9 GB/shard |
| Bốn shard, RF=3 | Bốn tập con, mỗi phần có ba bản | 108 GB | ~9 GB/replica-shard |

Như vậy, **phân mảnh làm nhỏ tập dữ liệu mà mỗi replica-shard phải quản lý**; **replication làm tăng số bản lưu để chịu lỗi**. Nếu RF không đổi, tăng số shard **không tự làm thay đổi tổng dữ liệu logic hay hệ số nhân bản**, nhưng có thể thay đổi overhead thực.

### 7.2. Không nhầm số document với byte hoặc throughput

Bốn shard mỗi shard ba triệu document không có nghĩa cân bằng tài nguyên:

- Một tenant có document chứa attachment lớn.
- Một shard có index khác do workload.
- Một nhóm Order bị update liên tục.
- Một shard nhận nhiều query có sort/aggregation nặng.

**Cân bằng số bản ghi không đồng nghĩa cân bằng byte, CPU, I/O hay QPS.**

## 8. Throughput: khi nào phân mảnh giúp tăng năng lực ghi?

Nếu một node xử lý tối đa `W` write/s cho workload đã đo, bốn shard có thể phục vụ nhiều write hơn khi các request được phân phối đều và các shard có tài nguyên đủ độc lập.

Tuy nhiên:

\[
\text{Cluster write throughput} \neq
\text{Số shard}\times \text{Throughput một shard}
\]

trong mọi điều kiện.

Những nút thắt có thể còn:

- Tất cả request tập trung vào **một shard**.
- Ghi phải qua coordinator, unique service, network hoặc một shared log.
- Secondary indexes, transaction và replication làm tăng chi phí.
- Application server/connection pool không scale tương ứng.
- Cross-shard transaction hoặc global aggregation trở thành bottleneck.
- Disk/network shared giữa nhiều shard trên cùng node.

### 8.1. Ví dụ workload phân bố đều

~~~text
Shard 0: 2.500 write/s
Shard 1: 2.500 write/s
Shard 2: 2.500 write/s
Shard 3: 2.500 write/s

Tổng: 10.000 write/s trong điều kiện minh họa.
~~~

Nếu workload đều và mỗi shard có thể chịu mức này, cluster có cơ hội scale-out tốt.

### 8.2. Ví dụ một shard nóng

~~~text
Shard 0: 8.500 write/s
Shard 1:   500 write/s
Shard 2:   500 write/s
Shard 3:   500 write/s
~~~

Nếu shard 0 chỉ chịu được 3.000 write/s, các shard còn lại rảnh **không giúp shard 0 tự xử lý 8.500 write/s**. Cần thay khóa/bucket/ownership hoặc cơ chế hạn chế tải, không chỉ thêm server.

### 8.3. Replication có thể tăng read throughput — có điều kiện

Nếu mỗi shard có nhiều replica, một số read được phân phối tới secondary/follower có thể tăng tổng read capacity. Nhưng:

- Read từ replica có thể stale.
- Một số strong read cần leader/quorum và không chia đều đơn giản.
- Mỗi replica tốn storage, CPU, network.
- Failover và replication lag phải được quan sát.

Không nên suy từ RF=3 rằng năng lực **write** mặc nhiên gấp ba.

## 9. Logical partition, shard, physical node và replica

Những từ này thường bị dùng thay nhau dù khác lớp trừu tượng.

| Thuật ngữ | Ý nghĩa thực dụng |
| --- | --- |
| **Logical partition** | Tập bản ghi được nhóm theo quy tắc khóa hoặc domain |
| **Shard** | Đơn vị phân phối dữ liệu/định tuyến ở lớp hệ thống; nghĩa cụ thể phụ thuộc engine |
| **Chunk/range/tablet/virtual partition** | Đơn vị nhỏ hơn được hệ tự điều chuyển hoặc ánh xạ |
| **Physical node** | Máy/instance/process chứa các phần dữ liệu |
| **Replica** | Một bản dữ liệu của một phạm vi shard/partition |
| **Shard key/partition key** | Thuộc tính được dùng để xác định vị trí hoặc nhóm dữ liệu |
| **Routing metadata** | Bản đồ từ khóa/range/token/partition tới owner hiện tại |
| **Coordinator/router** | Thành phần điều hướng request và hợp nhất phản hồi |

### 9.1. “Partition” có ít nhất ba nghĩa khác nhau

- **Data partition:** Một nhóm dữ liệu được chia theo khóa.
- **Physical partition/storage partition:** Đơn vị phân bổ tài nguyên của engine.
- **Network partition:** Sự cố mạng ngăn các node trao đổi message, xuất hiện trong ngữ cảnh CAP.

**Data sharding không phải network partition.** Một hệ có hàng nghìn data partitions vẫn có thể hoạt động trên mạng bình thường. Một hệ không hề chia dữ liệu mà chỉ nhân bản vẫn có thể gặp network partition.

### 9.2. Không mặc định một partition là một server

Ví dụ Cassandra:

~~~text
partition key -> token
token/range -> replica set theo ring/membership
physical node -> giữ nhiều token ranges và nhiều logical partitions
~~~

Ví dụ DynamoDB:

~~~text
Partition key -> hash -> internal physical partitions
~~~

Ứng dụng chọn partition key nhưng không trực tiếp nhìn thấy hay điều khiển một physical partition ứng với mỗi giá trị khóa.

Ví dụ Elasticsearch:

~~~text
Index -> một số primary shards -> replicas
Mỗi primary shard là đơn vị phân phối ở engine search.
~~~

**Tên gọi giống nhau không bảo đảm mapping giống nhau.**

## 10. Phân mảnh ngang và phân chia theo chiều dọc

### 10.1. Horizontal sharding

Các node giữ **những bản ghi khác nhau** nhưng cùng kiểu dữ liệu:

~~~text
Orders:
  Shard 0: Order A..F
  Shard 1: Order G..L
  Shard 2: Order M..R
  Shard 3: Order S..Z
~~~

Đây là sharding thường được đề cập khi nói scale-out collection/table NoSQL.

### 10.2. Vertical partitioning

Phân chia theo **thuộc tính hoặc nhóm dữ liệu**:

~~~text
User core: userId, name, email
User preferences: userId, theme, locale
User history: userId, events
~~~

Vertical partitioning có thể giảm kích thước bản ghi được đọc cho từng workload và cô lập domain, nhưng không tự đồng nghĩa horizontal sharding. Nếu một bảng `UserCore` vẫn lớn, nó vẫn có thể cần phân mảnh ngang.

### 10.3. Tách service theo domain cũng không hoàn toàn giống sharding

Tách `OrdersService`, `InventoryService`, `PaymentsService` giúp chia **trách nhiệm nghiệp vụ và dữ liệu**. Mỗi service có thể dùng database riêng và tự phân mảnh. Đó là lựa chọn kiến trúc domain/service boundary, không phải chỉ một shard key trên cùng logical collection.

## 11. Shard key: quyết định dữ liệu được đặt ở đâu

**Shard key** là thông tin mà hệ thống dùng để ánh xạ một bản ghi hoặc request tới shard. Một thiết kế khóa tốt phải tính đồng thời:

- **Phân bố dữ liệu và write:** Tránh dồn toàn bộ traffic vào một owner.
- **Query locality:** Những truy vấn thường dùng nên xác định được shard mà không fan-out.
- **Cardinality và skew:** Có đủ giá trị khóa hay không, tenant lớn có áp đảo không?
- **Khả năng tăng trưởng:** Khi thêm shard có cần di chuyển dữ liệu quá nhiều?
- **Tính ổn định của khóa:** Nếu shard key đổi thường xuyên, migration/routing sẽ phức tạp.
- **Phạm vi transaction và uniqueness:** Các entity cần kiểm tra cùng nhau có ở một shard/aggregate không?
- **Bảo mật:** TenantId từ ngữ cảnh xác thực phải được dùng nhất quán, không tin input không có quyền.

### 11.1. Một bảng đặt câu hỏi

| Query quan trọng | Thuộc tính có sẵn | Gợi ý ảnh hưởng shard key |
| --- | --- | --- |
| `GET /orders/{orderId}` | tenantId, orderId? | Có thể target nếu routing biết khóa |
| `GET /shops/{shopId}/orders` | tenantId, shopId | Nên cân nhắc locality theo shop |
| `GET /customers/{id}/orders` | tenantId, customerId | Có thể cần read model/index khác |
| Báo cáo tất cả tenant theo ngày | date range | Thường cần fan-out/OLAP |
| Cập nhật trạng thái một Order | orderId, tenantId | Nên target đúng owner |
| Trừ stock một SKU nóng | tenantId, sku | Một hot key có thể là bottleneck |

**Không có shard key hoàn hảo cho mọi query.** Hệ thống thường chọn tối ưu các truy vấn chủ đạo và xây thêm secondary indexes, read models hoặc analytical pipeline cho query khác.

## 12. Chiến lược 1: phân mảnh theo range

Range partitioning đặt bản ghi theo khoảng giá trị:

~~~text
Shard 0: createdAt < 2025-01-01
Shard 1: 2025-01-01 <= createdAt < 2025-07-01
Shard 2: 2025-07-01 <= createdAt < 2026-01-01
Shard 3: createdAt >= 2026-01-01
~~~

### 12.1. Ưu điểm

- Query có range predicate phù hợp có thể chỉ chạm một số shard.
- Dữ liệu gần nhau theo khóa có thể cùng đặt, hữu ích cho range scan và một số loại sort.
- Hệ thống có thể chia/tách những range lớn theo chính sách.

### 12.2. Nhược điểm

Với `createdAt` luôn tăng:

~~~text
Mọi Order mới -> range mới nhất -> Shard 3
~~~

Shard 3 thành **write hotspot**, trong khi các shard lịch sử chủ yếu phục vụ read.

Các trường hợp range chứa những tenant lớn hoặc giá trị skew còn gây mất cân bằng byte.

### 12.3. Khi nào phù hợp?

Range sharding có thể hợp lý nếu workload chủ yếu đọc **các khoảng thời gian cụ thể**, tốc độ ghi được phân phối theo nhiều range/bucket và hệ có cơ chế split/placement hợp lý. Không chọn `createdAt` làm một shard key duy nhất rồi kỳ vọng write tăng dần tự trải đều.

## 13. Chiến lược 2: hash-based sharding

Một cách minh họa:

\[
\text{shardId}=\operatorname{hash}(\text{key})\bmod N
\]

Với `N=4`, các Order ID khác nhau có thể được phân phối gần đều hơn nếu hash thích hợp.

~~~text
hash(O901) -> Shard 0
hash(O902) -> Shard 2
hash(O903) -> Shard 1
hash(O904) -> Shard 3
~~~

Các shard ID chỉ để minh họa, không phải kết quả tính từ một hàm hash cụ thể.

### 13.1. Ưu điểm

- Trải những khóa có giá trị gần nhau sang nhiều shard.
- Giảm nguy cơ mọi write của khóa **tăng dần** đổ vào một range mới nhất.
- Point lookup có full shard key thường định tuyến được.

### 13.2. Nhược điểm

- Range query theo trường bị hash có thể cần nhiều shard.
- Các Order của cùng shop có thể nằm rải rác nếu hash theo `orderId`.
- Khi số shard vật lý đổi từ 4 sang 5, công thức modulo đơn giản có thể **ánh xạ lại rất nhiều key**.

Trong sản phẩm thật, hệ có thể dùng token ranges, consistent hashing, virtual nodes, buckets hoặc routing metadata để giảm chi phí remap. **Không mặc định mọi database dùng đúng `hash % số server`.**

### 13.3. Hot key không tự biến mất bằng hash

Hash phân tán **nhiều khóa khác nhau**; nó không tự chia **một khóa rất nóng**. Nếu tất cả write nhắm `inventory:SKU-7`, hash của key đó vẫn trỏ về cùng một owner logical. Để mở rộng, cần đổi mô hình (chẳng hạn phân bổ escrow stock theo kho), không chỉ thêm shard.

## 14. Chiến lược 3: tenant-based sharding

Với SaaS đa tenant, có thể dùng:

~~~text
shard = route(tenantId)
~~~

Các Order của một tenant được đặt cùng một shard:

~~~text
Tenant A, B, C -> Shard 0
Tenant D, E    -> Shard 1
Tenant F, G, H -> Shard 2
Tenant I, J    -> Shard 3
~~~

### 14.1. Điểm mạnh

- Các query luôn có `tenantId` có thể target một shard.
- Một số thao tác bên trong tenant có locality tốt hơn.
- Có thể phân bổ tenant lớn sang hạ tầng chuyên biệt.
- Hỗ trợ những chính sách placement/data residency theo tenant.

### 14.2. Hạn chế

Giả sử:

~~~text
Tenant A: 8.000.000 Order
Tenant B:    10.000 Order
Tenant C:    15.000 Order
~~~

Nếu `tenantId` là đơn vị phân mảnh **không thể chia nhỏ**, Tenant A có thể làm một shard quá tải. Các shard chứa B/C vẫn còn tài nguyên.

Giải pháp có thể là:

- Tách tenant lớn thành các **buckets** với routing xác định.
- Dùng `tenantId + shopId` hoặc `tenantId + bucket` làm đơn vị placement.
- Đưa tenant đặc biệt vào cụm riêng nếu isolation/routing phù hợp.
- Duy trì directory cho phép thay đổi owner của tenant hoặc bucket.

Nhưng chia tenant thành nhiều buckets khiến query `all orders of tenant` cần hợp nhất nhiều shard và có thể làm transaction xuyên bucket khó hơn.

### 14.3. Cách thiết kế truy vấn phải đi cùng khóa

Nếu sharding theo `tenantId`, một API:

~~~http
GET /orders/O900
~~~

chưa chắc định tuyến được nếu **chỉ có `orderId` mà không biết tenant**. Có thể yêu cầu context xác thực chứa tenantId hoặc có một directory `orderId -> tenant/bucket`.

Không tin một `tenantId` bất kỳ do client gửi nếu nó có thể cho phép đọc Order của tenant khác.

## 15. Directory-based sharding

Thay vì tính shard bằng một hàm hash cố định, hệ có thể giữ một bảng ánh xạ:

~~~text
tenant-a -> Shard 0
tenant-b -> Shard 2
tenant-c -> Shard 1
tenant-d -> Shard 3
~~~

**Directory** cho phép di chuyển một tenant/bucket sang owner mới bằng cách thay metadata sau một quy trình migration.

### 15.1. Ưu điểm

- Chủ động đặt tenant lớn trên tài nguyên phù hợp.
- Có thể quản lý placement địa lý hoặc isolation theo workload.
- Hạn chế việc thay hash mapping khi mở rộng hạ tầng.

### 15.2. Chi phí

- Directory phải được **đọc nhanh, quản lý phiên bản và có độ sẵn sàng** phù hợp.
- Cache routing có thể stale khi tenant đang chuyển shard.
- Quy trình cutover cần bảo đảm không có hai owner cùng nhận write không điều kiện.
- Routing metadata là một thành phần quan trọng của đường request, không được xem nhẹ.

Với hệ có proxy/router chuyên biệt, ứng dụng có thể không trực tiếp nhìn thấy directory; nó vẫn tồn tại ở một lớp nào đó trong kiến trúc.

## 16. Định tuyến: targeted query và scatter–gather

Với bốn shard, một router có thể xử lý:

~~~mermaid
flowchart LR
    C["API request"] --> R["Router / coordinator"]
    R -->|Targeted query| S2["Shard 2"]
    R -.->|Scatter khi thiếu shard key| S0["Shard 0"]
    R -.->|Scatter| S1["Shard 1"]
    R -.->|Scatter| S3["Shard 3"]
~~~

### 16.1. Targeted query

Nếu shard key là `tenantId` và request có tenant context:

~~~text
GET orders WHERE tenantId='merchant-a' AND orderId='O900'
              |
          Router knows tenantId
              |
          Only Shard 2
~~~

Router chỉ gửi tới shard chứa tenant, rồi có thể dùng index **bên trong shard** để tìm Order.

### 16.2. Scatter–gather

Nếu query không chứa đủ thông tin routing:

~~~text
GET orders WHERE status='PAID' ORDER BY createdAt DESC LIMIT 20
~~~

Router có thể phải:

1. Gửi query tới nhiều hoặc tất cả shard.
2. Mỗi shard lọc/sort một phần.
3. Nhận dữ liệu trung gian.
4. Merge, sort toàn cục và áp `LIMIT`.

**`LIMIT 20` không có nghĩa mỗi shard không phải đọc nhiều dữ liệu**. Chi phí còn phụ thuộc index, local sort, network và cách engine thực thi distributed top-k.

### 16.3. Chi phí latency

Với một query fan-out tới bốn shard, tổng thời gian thường chịu ảnh hưởng của:

~~~text
router overhead
+ shard query latency của nhánh chậm
+ network/serialization
+ merge/global sort
~~~

Không được cộng máy móc latency cả bốn shard nếu chúng thực thi song song; cũng không được lấy trung bình và bỏ shard chậm, vì fan-out thường phải **đợi các phần cần thiết** để trả kết quả đúng.

### 16.4. Khi nào scatter–gather chấp nhận được?

- Query quản trị hoặc phân tích chạy ít.
- Batch/OLAP với budget thời gian riêng.
- Kết quả không cần real-time quá thấp.
- Fan-out được giới hạn và index/read model phù hợp.

Nếu một API chính có SLO p95 chặt và mọi request đều scatter đến hàng trăm shard, cần xem lại shard key, read model hoặc hệ analytical chuyên biệt.

## 17. Sharding và secondary index

Shard key giúp xác định **vị trí**, còn secondary index giúp truy cập nhanh **bên trong phạm vi dữ liệu** hoặc qua một mô hình index phân tán tùy engine.

Ví dụ shard theo tenant:

~~~text
Shard 2:
  tenant merchant-a
  Index (shopId, status, createdAt)
~~~

Query có `tenantId` có thể tới Shard 2 và dùng index tại shard ấy.

Nếu query chỉ có `customerEmail`, secondary index local trên từng shard **không nhất thiết** giúp router biết shard nào phải truy cập. Có thể cần:

- Fan-out tới các local indexes.
- Một **global lookup index/directory**: `email -> tenantId / customerId`.
- Một read model được phân mảnh theo `email` cho access pattern đó.

### 17.1. Global secondary index là một hệ dữ liệu khác cần vận hành

Một global index phân phối khóa theo cách khác với bảng gốc có thể giúp query không dùng shard key, nhưng phát sinh:

- Chi phí ghi thêm.
- Đồng bộ index với dữ liệu nguồn.
- Quy tắc consistency/freshness.
- Routing từ index entry tới document.
- Xử lý xóa hoặc update khóa index.

Không thể chỉ nói “thêm index là mọi query sẽ target một shard”.

## 18. Cross-shard join, transaction và uniqueness

Sharding đem lại tài nguyên phân tán nhưng một số ràng buộc khó hơn.

### 18.1. Join/aggregation

Nếu Order và Customer nằm ở hai shard khác nhau, truy vấn join có thể cần:

- Chuyển dữ liệu qua mạng.
- Remote lookup theo mỗi dòng.
- Broadcast/partitioned join.
- Pre-joined read model hoặc denormalization.

Với NoSQL, các nhóm thường **thiết kế dữ liệu theo access pattern** để tránh join xuyên shard trong đường request nóng. Nhưng denormalization làm tăng trách nhiệm đồng bộ khi source thay đổi.

### 18.2. Transaction nhiều shard

Một transaction cập nhật Order ở Shard A và Inventory ở Shard B có thể phải phối hợp nhiều participant:

~~~text
Transaction coordinator
       /        \
  Shard A      Shard B
  Order        Inventory
~~~

Nếu engine hỗ trợ distributed transactions, chúng thường có chi phí coordination, network, failure handling và timeout cao hơn thao tác trên một owner. Không phải hệ NoSQL nào cũng hỗ trợ hoặc cho cùng bảo đảm.

Nếu nghiệp vụ cần strong invariant thường xuyên, cân nhắc:

- Gộp dữ kiện có ràng buộc chặt vào cùng aggregate/partition khi hợp lý.
- Dùng conditional transaction trong phạm vi engine hỗ trợ.
- Tách workflow có trạng thái, idempotency và compensation khi không thể commit atomically.

**Colocate không tự thay thế transaction**, nhưng có thể giảm số participant cần phối hợp.

### 18.3. Uniqueness toàn cục

Giả sử `email` phải unique trên toàn hệ. Nếu email không phải shard key và mỗi shard chỉ có unique index cục bộ:

~~~text
Shard 0: email=lan@example.test
Shard 1: email=lan@example.test
~~~

Hai shard có thể chấp nhận cùng email nếu không có cơ chế uniqueness toàn cục.

Các hướng:

- Dùng chính email chuẩn hóa làm khóa dẫn tới một authority duy nhất cho đăng ký.
- Có global reservation/unique-key registry dùng conditional write.
- Dùng tính năng global uniqueness của engine nếu có và **đáp ứng điều kiện shard key/index**.

Không mặc định unique index local đảm bảo unique **xuyên shards**.

### 18.4. ID toàn cục

Một Order ID có thể được tạo bằng UUID/ULID hoặc một hệ cấp ID. Dù ID global unique, **router vẫn cần biết mapping tới shard**. Unique ID là vấn đề **định danh**, còn shard key là vấn đề **vị trí và truy cập**.

## 19. Data skew: nhiều shards nhưng một shard quá lớn

Giả sử 12 triệu Order chia theo `tenantId`, thực tế:

~~~text
Shard 0: 7.000.000 Order
Shard 1: 2.000.000 Order
Shard 2: 2.000.000 Order
Shard 3: 1.000.000 Order
~~~

Shard 0 chiếm phần lớn tập dữ liệu; các node khác còn đĩa trống. Đó là **data skew**.

### 19.1. Các dạng lệch khác nhau

| Dạng | Dấu hiệu | Nguyên nhân phổ biến |
| --- | --- | --- |
| Storage skew | Một shard gần đầy disk | Tenant lớn hoặc document size khác |
| Write skew | Một shard nhiều write/s | Hot tenant/key, time range mới |
| Read skew | Một shard có p95 cao | Truy vấn nóng hoặc cache thấp |
| CPU skew | Một owner bị bão hòa CPU | Aggregation/scan/sort phức tạp |
| Network skew | Node truyền nhiều byte hơn | Large payload, fan-out, replica sync |
| Index skew | Index size/cache miss lệch | Workload và phân bố field khác |

### 19.2. Thêm node không chắc giải quyết hot key

Nếu một tenant độc nhất tạo 80% lưu lượng và tất cả dữ liệu tenant nằm trong một shard **không được tách**, thêm ba node mới vẫn không làm hot tenant tự chia tải.

Giải pháp đòi **thay đơn vị phân mảnh** (bucket/tenant+shop/range khác) hoặc thiết kế cơ chế chia quyền/ghi song song nếu domain cho phép.

## 20. Hot partition/hot key và cách khắc phục

### 20.1. Time-based hotspot

Shard key tăng dần theo thời gian có thể đẩy write mới vào cuối range.

Hướng xử lý:

- Hash/bucket một phần khóa.
- Chia write thành nhiều logical partitions có routing rõ.
- Tách time bucket nhưng vẫn tránh một bucket quá nóng.
- Nếu dữ liệu chỉ append, cân nhắc pipeline/batch ingestion phù hợp.

### 20.2. Tenant hotspot

Nếu một merchant có hàng triệu Order và traffic cao, `tenantId` đơn lẻ có thể quá thô.

Một giải pháp minh họa:

~~~text
bucket = stableHash(orderId) % 16
partitionKey = tenantId + "#" + bucket
~~~

Với 16 bucket logic, write có thể trải lên nhiều owner **nếu routing thực sự phân bổ bucket và các node có tài nguyên độc lập**.

Nhưng query:

~~~text
Liệt kê mọi Order của tenant
~~~

giờ có thể phải truy cập **16 buckets** và merge theo thời gian. Đổi lại throughput có thể tăng nhưng chi phí đọc tăng.

### 20.3. Một inventory SKU nóng

Nếu một mặt hàng có stock còn 1, ta cần một authority để không bán hai lần. Chia một counter duy nhất ra 16 shard mà không có quy tắc sẽ tạo oversell.

Một cách đúng nghiệp vụ có thể là **phân bổ quota/escrow**:

~~~text
Stock tổng = 100
Warehouse A được cấp quyền bán 60
Warehouse B được cấp quyền bán 40
~~~

Mỗi nơi trừ trong quota được cấp; chuyển quyền phải an toàn. Đây là **thay mô hình invariant**, không đơn giản là đặt thêm shard.

## 21. Resharding: chia lại dữ liệu khi tăng trưởng

Sau vài tháng, một shard có thể đầy hoặc quá tải. Muốn thêm node, phải quyết định **dữ liệu nào chuyển đi** và cập nhật định tuyến.

### 21.1. Luồng resharding khái niệm

~~~mermaid
flowchart TD
    A["Shard quá tải / cần thêm node"] --> B["Chọn ranges hoặc buckets sẽ chuyển"]
    B --> C["Chuẩn bị owner mới và metadata"]
    C --> D["Copy dữ liệu nền / snapshot"]
    D --> E["Bắt kịp writes phát sinh trong lúc copy"]
    E --> F["Thiết lập cutover và fencing"]
    F --> G["Cập nhật routing epoch / map"]
    G --> H["Xác minh dữ liệu, traffic, invariant"]
    H --> I["Dọn bản cũ sau cửa sổ an toàn"]
~~~

Đây là **mô hình khái niệm**. Sản phẩm thực có balancer/chunk migration/token movement/resharding với từng quy trình cụ thể; không tự triển khai hai writer song song nếu không hiểu giao thức engine.

### 21.2. Rủi ro trong quá trình chuyển

Trong khi copy 100 GB, application vẫn ghi Order mới:

~~~text
T1: Copy snapshot từ owner A.
T2: User update O900 trên A.
T3: Cutover O900 sang owner B.
~~~

Nếu B chỉ có snapshot cũ, update ở T2 có thể **bị mất**. Cần change stream/log catch-up, write coordination hoặc phương pháp migration đáng tin cậy.

### 21.3. Routing metadata stale

Client A cache mapping `tenant-a -> Shard 1`, nhưng sau cutover owner mới là Shard 3. Nếu application vẫn ghi Shard 1, có thể tạo **hai nguồn cùng nhận write**.

Cần quy tắc:

- Routing version/epoch.
- Redirect/forwarding hoặc refresh metadata.
- Chặn writer cũ bằng fencing/ownership checks.
- Idempotency cho retry khi route thay đổi.
- Observability về stale route/failed forwards.

### 21.4. Không đánh giá resharding chỉ bằng thời gian copy

Các metric cần:

- Bytes moved, migration throughput.
- Backfill/catch-up lag.
- Write p95/p99 lúc migration.
- Disk/RAM/network overhead.
- Số query bị retry/timeout.
- Time-to-cutover và thời gian rollback.
- Correctness check theo key/count/hash/version phù hợp.

**Thêm shard** có thể tốn chi phí vận hành lớn; cần đủ **headroom** trước khi nguồn cũ đầy đĩa.

## 22. Shard placement và fault domain

Một shard có RF=3 nhưng cả ba replica nằm trên **cùng một physical host** sẽ không giúp chịu lỗi host đó. Ba replica trên ba VM cùng một điểm lỗi hạ tầng có thể cũng không đạt mục tiêu.

Khi bố trí cần cân nhắc:

- Host/instance.
- Rack.
- Availability Zone.
- Datacenter/region.
- Network failure domain.
- Chính sách data residency/compliance.

### 22.1. Cùng một phần dữ liệu, nhiều vị trí

~~~text
Shard 0:
  Replica 0 in AZ-a
  Replica 1 in AZ-b
  Replica 2 in AZ-c
~~~

Mục tiêu là không để một lỗi đơn lẻ làm mất mọi bản của shard. Nhưng **placement chỉ tạo điều kiện chịu lỗi**; giao thức failover, consistency và recovery vẫn cần được thiết kế.

### 22.2. Sharding và network partition trong CAP

Khi một AZ mất liên lạc:

- Một shard có đủ replica ở phía majority có thể tiếp tục.
- Một shard khác có placement/quorum không phù hợp có thể bị chặn.
- Read yếu có thể tiếp tục nhưng stale nếu API cho phép.

Sharding quyết định **phạm vi dữ liệu và chủ sở hữu**, replication quyết định **các bản và failure domains**, còn CAP/consensus giúp phân tích **những operation nào được phục vụ khi replica mất liên lạc**.

## 23. Không đồng nhất replication với consistency

Có nhiều bản của cùng dữ liệu **không đồng nghĩa** mọi read luôn thấy write mới nhất.

### 23.1. Replication bất đồng bộ

~~~text
T1: Primary cập nhật Order v11.
T2: Primary trả SUCCESS.
T3: Secondary vẫn ở v10.
T4: Client đọc từ secondary thấy v10.
T5: Secondary bắt kịp v11.
~~~

Nếu read contract chỉ hứa **eventual consistency**, kết quả tại T4 có thể nằm trong mức độ trễ được chấp nhận. Nếu API hứa read-after-write mạnh, cần read path/session/quorum thích hợp.

### 23.2. Replication đồng bộ/majority

Ack sau khi đủ replica tham gia có thể tăng bảo đảm về durability hoặc commit, nhưng không tự cho phép **mọi replica bất kỳ** trả strong read. Read protocol và write protocol phải tương thích; xem thêm term, barrier, consistency mode và election.

### 23.3. Một shard nhiều replica không cho phép hai owner ghi mù

Nếu hai replica của cùng shard cùng chấp nhận update mâu thuẫn khi partition mà không có coordination, có thể xảy ra conflict hoặc lost intent. Replication cần **quy tắc ownership/commit/conflict resolution**, không chỉ nhân bản byte.

## 24. MongoDB: sharded cluster và replica set

MongoDB là ví dụ rõ để phân biệt hai lớp:

- Một **sharded cluster** phân phối collection theo shard key và metadata.
- Mỗi **shard** trong cấu hình triển khai thường là **replica set** để có redundancy.
- **`mongos`** định tuyến request dựa trên shard key và routing metadata.

Sơ đồ khái niệm:

~~~text
Application
    |
  mongos/router
    |
    +---- Shard 0 / Replica Set 0
    |       primary + secondaries
    |
    +---- Shard 1 / Replica Set 1
    |       primary + secondaries
    |
    +---- Shard 2 / Replica Set 2
            primary + secondaries
~~~

### 24.1. Định nghĩa shard key

Ví dụ `orders` có các field:

~~~javascript
{
  tenantId: "merchant-a",
  orderId: "O900",
  shopId: "shop-12",
  createdAt: ISODate("2026-11-14T09:30:00Z")
}
~~~

Một shard key minh họa có thể là:

~~~javascript
{ tenantId: 1, orderId: "hashed" }
~~~

**Lưu ý:** MongoDB có các quy tắc cụ thể về cấu trúc shard key, hashed indexes và các thao tác cho phép tùy phiên bản; ví dụ chỉ nhằm thể hiện ý tưởng kết hợp tenant context với thành phần phân phối. Cần xem syntax và khả năng hỗ trợ của phiên bản thực trước khi áp dụng.

Một cách tiếp cận khác là shard theo tiền tố `tenantId` khi mục tiêu là locality theo tenant, nhưng cần phân tích tenant lớn có tạo hotspot hay không.

### 24.2. Targeted và scatter trong MongoDB

Query mang đủ shard key hoặc shard-key prefix phù hợp với routing có thể target ít shard hơn.

~~~javascript
db.orders.find({
  tenantId: "merchant-a",
  orderId: "O900"
});
~~~

Nếu query không cho router xác định owner:

~~~javascript
db.orders.find({
  status: "PAID"
}).sort({ createdAt: -1 }).limit(20);
~~~

Nó có thể phải gửi đến nhiều shard và merge kết quả. Secondary index ở từng shard không tự làm query không có shard key thành single-shard query.

### 24.3. Balancer và chunk/range

MongoDB có cơ chế quản lý các phạm vi shard key, metadata và di chuyển dữ liệu tùy phiên bản. Khi đánh giá cần xem:

- Dung lượng và phân bố data chunks/ranges.
- Balancer/resharding load.
- Indexes phù hợp shard key và query.
- Truy vấn target bao nhiêu shard.
- Replica set health bên trong từng shard.
- Read/write concerns và failover semantics.

Không dùng một con số kích thước chunk hoặc quy tắc shard-key toàn cục như thể bất biến ở mọi phiên bản MongoDB.

### 24.4. Unique indexes và transactions

Một unique index trong sharded collection có những **ràng buộc liên quan shard key** theo khả năng MongoDB. Không mặc định unique email toàn cục nếu email ở nhiều shard không có cơ chế thích hợp.

MongoDB hỗ trợ một số transaction xuyên shard nhưng có chi phí và giới hạn theo phiên bản/topology; giảm số participant có thể có lợi khi thiết kế aggregate.

## 25. Cassandra/ScyllaDB: partition key, token và replication factor

Trong wide-column database, **partition key** được dùng để ánh xạ row vào **logical partition/token**. Token/ranges gắn với các node theo chiến lược placement và **replication factor**.

Ví dụ CQL:

~~~sql
CREATE TABLE orders_by_shop_day (
    tenant_id text,
    shop_id text,
    day_utc date,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, day_utc),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Ở đây:

~~~text
Partition key: (tenant_id, shop_id, day_utc)
Clustering:    created_at DESC, order_id ASC
~~~

### 25.1. Vì sao partition key quyết định hiệu năng?

Query biết đầy đủ partition key:

~~~sql
SELECT created_at, order_id, status
FROM orders_by_shop_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND day_utc = '2026-11-14'
LIMIT 20;
~~~

có thể target logical partition liên quan. Nếu API phải lấy bảy ngày, nó cần đọc nhiều day partitions và merge phía ứng dụng/coordinator theo mô hình đã thiết kế.

### 25.2. Chọn partition quá lớn

Nếu partition key chỉ là `(tenant_id)` và một merchant có hàng triệu Order, logical partition có thể rất lớn, gây:

- Read amplification.
- Tombstone/compaction pressure.
- Hot partition.
- Latency cao cho partition lớn.

Bucket theo ngày/shop có thể giảm kích thước và phân bổ tốt hơn, nhưng query xuyên ngày/shop cần fan-out.

### 25.3. Replication factor không phải số partition

Giả sử RF=3: mỗi logical partition có các bản trên các replica phù hợp chiến lược replication. Điều này **không có nghĩa toàn bảng bị chia thành ba phần**.

Các node thường giữ **nhiều logical partitions/token ranges**, chứ không phải mỗi node chỉ có đúng một partition.

Đọc/ghi với mức consistency như `ONE`, `QUORUM`, `LOCAL_QUORUM` có thể yêu cầu số replica khác nhau, nên read latency, fault tolerance và khả năng phục vụ khi mất mạng khác nhau. Những mức này không tự bảo đảm mọi transaction hoặc uniqueness toàn cục.

## 26. DynamoDB: partition key và internal partitions

DynamoDB là hệ quản lý placement và physical partitions ở phía dịch vụ. Ứng dụng thiết kế **partition key**, nhưng không trực tiếp chọn server cho mỗi item.

Ví dụ bảng:

~~~text
PK = TENANT#merchant-a#SHOP#shop-12#DAY#2026-11-14
SK = 2026-11-14T09:30:00Z#O900
~~~

### 26.1. Partition key định vị tập item

Một `Query` với PK đầy đủ có thể tìm những item thuộc partition key và dùng sort key. Nếu tất cả write dồn vào **một PK cực nóng**, cần đánh giá hot-key/hot-partition trong capacity thực.

### 26.2. Write sharding bằng bucket

Để phân phối tải, có thể thêm bucket vào PK:

~~~text
PK = TENANT#merchant-a#SHOP#shop-12#DAY#2026-11-14#B0
PK = TENANT#merchant-a#SHOP#shop-12#DAY#2026-11-14#B1
PK = TENANT#merchant-a#SHOP#shop-12#DAY#2026-11-14#B2
PK = TENANT#merchant-a#SHOP#shop-12#DAY#2026-11-14#B3
~~~

Bucket có thể được tính từ Order ID để phân phối. Nhưng API “đơn mới nhất của shop trong ngày” phải query **nhiều buckets** rồi merge. Không tăng bucket vô hạn mà quên chi phí đọc.

### 26.3. GSI và projection

Global secondary index có thể hỗ trợ access pattern khác theo PK/SK của chính GSI, nhưng:

- Tạo thêm chi phí lưu trữ/ghi.
- Có quy tắc consistency/projection riêng.
- Có thể sinh hotspot theo khóa mới.

Không coi GSI là “bản sao đầy đủ của table và mọi query đều strong” nếu cấu hình không hỗ trợ.

### 26.4. Replication được dịch vụ quản lý

DynamoDB quản lý replication/độ bền theo mô hình sản phẩm, còn **global tables** cung cấp lựa chọn multi-region replication với những semantics riêng. Không suy một table có RF trực tiếp do ứng dụng chọn giống Cassandra, hoặc việc thêm một region tự tăng write capacity cho **cùng một item cần quyết định nhất quán toàn cầu**.

## 27. Elasticsearch/OpenSearch: primary shards và replica shards

Với search engine, phân biệt rất trực quan:

~~~text
Index "orders-search"
      |
      +-- Primary shard 0 ---> Replica shard 0
      +-- Primary shard 1 ---> Replica shard 1
      +-- Primary shard 2 ---> Replica shard 2
~~~

- **Primary shards** chia index thành nhiều đơn vị dữ liệu khác nhau.
- **Replica shards** là các bản sao của từng primary shard.
- Query search có thể được xử lý trên các bản shard phù hợp, rồi coordinator tổng hợp kết quả.

### 27.1. Tăng replica khác tăng primary shard

Nếu index có 3 primary shards và 1 replica cho mỗi primary:

~~~text
Logical primary shards = 3
Total shard copies     = 3 × (1 primary + 1 replica) = 6
~~~

Tăng replica count có thể giúp **read/search capacity và chịu lỗi**, nhưng cũng tăng dung lượng và replication/indexing overhead.

Thay đổi số primary shards ảnh hưởng **cách dữ liệu logic được chia**, có thể cần những thao tác split/shrink/reindex tùy phiên bản và điều kiện. Không kỳ vọng thêm replica giải quyết một primary shard quá lớn hoặc hot như thêm phần dữ liệu logic độc lập.

### 27.2. Search fan-out

Một query tìm kiếm toàn index có thể chạm nhiều primary-shard groups. Query latency chịu ảnh hưởng của nhánh chậm và bước merge top hits. Nhiều primary shards quá mức có thể tăng coordination overhead; quá ít shards có thể hạn chế phân phối tải.

### 27.3. Search index thường là read model

Nếu Order chuẩn nằm ở một DB khác và search index được cập nhật qua event/CDC, cần đo **indexing lag và consistency contract**. Tìm nhanh bằng nhiều shard/replica không đồng nghĩa quyết định giữ hàng/quyền truy cập có thể dựa trực tiếp vào kết quả search.

## 28. Redis Cluster: hash slots không phải replica

Redis Cluster dùng **hash slots** để phân phối key giữa các master/owner theo cơ chế cluster. Một chi tiết phổ biến là **16.384 hash slots**.

~~~text
Key -> hash slot -> node owner
~~~

Node khác có thể giữ **replica** của owner để hỗ trợ failover; replica **không phải một hash slot độc lập với tập key khác**.

### 28.1. Ví dụ phân bố

~~~text
Master A: subset of hash slots, keys A...
Master B: subset of hash slots, keys B...
Master C: subset of hash slots, keys C...

Replica A': copy of data managed by Master A
Replica B': copy of data managed by Master B
Replica C': copy of data managed by Master C
~~~

Thêm một master và chuyển hash slots là thay đổi **phân bố key**. Thêm replica cho Master A là thêm bản sao **cùng tập key của A**. Hai hành động có mục tiêu khác nhau.

### 28.2. Multi-key operation

Các lệnh nhiều key trên Redis Cluster có yêu cầu **cùng hash slot** trong những trường hợp tương ứng. Hash tags có thể giúp đặt các key liên quan vào cùng slot:

~~~text
cart:{tenant-a:user-42}:items
cart:{tenant-a:user-42}:metadata
~~~

Nhưng nếu dồn quá nhiều key/hot traffic vào cùng một slot, lại tạo hotspot. **Colocation để hỗ trợ multi-key operation** và **phân tán tải** là hai mục tiêu cần cân bằng.

### 28.3. Replication và failover

Redis primary–replica replication có thể bất đồng bộ theo cấu hình. Failover không tự bảo đảm mọi write đã được client thấy thành công đều sẽ bền vững trong mọi lịch lỗi; cần hiểu ack, persistence và cluster behavior.

## 29. Giám sát: làm sao biết thật sự đang scale-out?

Chỉ đếm “cluster có 20 node” không đủ. Nên đo theo **shard, node, tenant, query shape và replica**.

| Nhóm metric | Cần xem |
| --- | --- |
| Data balance | Logical bytes, document/item count, index size từng shard |
| Write distribution | Writes/s theo shard, theo partition key/tenant |
| Read distribution | Reads/s, targeted vs scatter queries |
| Hotspot | p95/p99, CPU, disk I/O, network, queue từng owner |
| Routing | Number of shards contacted, stale metadata, retries |
| Replication | Lag, replica health, quorum availability, elections |
| Migration | Bytes moved, time-to-rebalance, catch-up lag |
| Capacity | Disk headroom, memory working set, compaction |
| Error | Timeouts, throttling, unavailable, failed routing |
| Correctness | Missing/duplicate rows, stale read, invariant violation |

### 29.1. Ví dụ đọc một dashboard

~~~text
Cluster writes: 10.000/s
Shard 0: 8.000/s
Shard 1:   700/s
Shard 2:   650/s
Shard 3:   650/s
~~~

Tổng throughput cao nhưng có **shard 0 quá nóng**. Thêm một replica của shard 0 có thể hỗ trợ read/failover, nhưng chưa chắc tăng write capacity của logical shard 0. Cần xem shard key, partitioning của workload và quyền ghi.

### 29.2. So trước và sau khi thêm shard

Một thí nghiệm nên giữ điều kiện tương đương:

~~~text
same dataset/query mix
same client concurrency
same read/write consistency
same replication factor
same workload distribution
same cache-state category
~~~

Rồi ghi:

~~~text
completed QPS
p50/p95/p99
error/throttle rate
per-shard CPU/bytes/lag
targeted query ratio
cross-shard query/transaction ratio
~~~

Không tuyên bố “scale tuyến tính” chỉ vì tổng CPU của nhiều node tăng, hoặc vì benchmark chỉ dùng các key được hash đều mà production lại có hot tenant.

## 30. Tình huống thiết kế: một SaaS có tenant lớn và nhỏ

Giả sử sản phẩm có:

~~~text
Tenant A: 8 triệu Order, write cao.
Tenant B: 80.000 Order, write thấp.
Tenant C: 40.000 Order, read nhiều.
Tenant D: 20.000 Order, ít truy cập.
~~~

Yêu cầu:

- Mỗi request luôn có `tenantId` từ ngữ cảnh xác thực.
- API `GET /shops/{shopId}/orders` rất phổ biến.
- API `GET /orders/{orderId}` phải có p95 thấp.
- Báo cáo toàn bộ tenant chạy ngoài luồng realtime.
- Tenant A không được làm tenant B/C quá chậm.

### 30.1. Phương án A: shard theo tenant

Ưu điểm:

- Định tuyến đơn giản bằng tenant.
- Query theo tenant có locality tốt.
- Dễ quản lý placement cho nhiều tenant nhỏ.

Nhược điểm:

- A quá lớn có thể khiến một shard hotspot.
- Query/transaction của A khó scale-out nếu luôn ở một owner.

### 30.2. Phương án B: tenant + bucket

~~~text
partitionKey = tenantId + "#" + stableHash(orderId) % bucketCount
~~~

Ưu điểm:

- Có thể phân phối Order của A trên nhiều shard owner.
- Point lookup khi biết tenantId và orderId có thể tính bucket.

Nhược điểm:

- Query danh sách Order của tenant/shop phải quét nhiều bucket và merge.
- Đổi bucketCount trực tiếp có thể làm routing phức tạp; cần versioned mapping/migration.
- Một số transaction cần cập nhật nhiều bucket.

### 30.3. Phương án C: read models theo truy vấn

Giữ nguồn Order được phân mảnh để xử lý write, đồng thời tạo:

~~~text
orders_by_shop_day
orders_by_customer
daily_shop_summary
~~~

Mỗi read model có partition key riêng theo query quan trọng. Đổi lại:

- Write amplification và thêm storage.
- Lag/consistency của pipeline cập nhật.
- Phải xử lý event trùng, event đến sai thứ tự và backfill.

### 30.4. Đề xuất cách chọn

Không chọn phương án từ cảm giác. Hãy đo:

1. Tỷ lệ traffic theo tenant và shop.
2. Số Order/bytes theo tenant.
3. Độ tập trung của hot keys.
4. Những query cần strong consistency và những query chịu eventual.
5. Chi phí fan-out khi bucket hóa.
6. Khả năng resharding và phân bổ replica theo failure domain.
7. SLO và ngân sách vận hành.

Một giải pháp có thể dùng **tenant placement cho tenant nhỏ**, còn tenant lớn được chuyển sang **nhiều buckets hoặc hạ tầng chuyên biệt**, với routing metadata rõ ràng.

## 31. Các sai lầm thường gặp

| Nhận định sai | Vì sao không đúng | Hướng sửa |
| --- | --- | --- |
| “Thêm replica là chia dữ liệu ra.” | Replica lưu cùng phần dữ liệu | Dùng shard để chia tập logic |
| “Tạo 4 shard là có 4 bản dự phòng.” | Mỗi shard có thể chỉ có một bản | Xác định RF và failure domains |
| “4 shard, RF=3 nghĩa có 12 máy.” | 12 replica placements có thể nằm trên ít/nhiều node | Phân biệt node và replica |
| “Replication luôn tăng write throughput.” | Ghi cùng logical key vẫn cần coordination | Phân phối write bằng shard hoặc đổi model |
| “Sharding luôn làm read nhanh.” | Fan-out/merge/network có thể chậm | Targeted query và access pattern |
| “Chia đều document là chia đều tải.” | Byte, CPU và QPS có thể lệch | Đo nhiều metric từng shard |
| “Hash sẽ hết hot key.” | Một key vẫn đến cùng owner | Bucket/escrow theo semantics |
| “Range theo createdAt tự trải write.” | Write mới dồn range cuối | Xử lý monotonic hotspot |
| “Đổi N trong hash%N là thêm node dễ dàng.” | Có thể remap nhiều key | Dùng virtual buckets/routing metadata |
| “Một partition bằng một server.” | Mapping theo engine khác nhau | Phân biệt logical/physical |
| “Query có index thì chỉ chạm một shard.” | Index local không biết owner khi thiếu shard key | Routing key/global lookup/read model |
| “Unique index local luôn unique toàn cầu.” | Hai shards có thể nhận cùng value | Global uniqueness authority |
| “Đọc replica nào cũng mới nhất.” | Replication lag/consistency | Chọn read mode đúng |
| “RF=3 thay backup.” | Xóa nhầm được nhân bản | Backup và thử restore |
| “Thêm shard không ảnh hưởng transaction.” | Có thể cần coordination xuyên shard | Thiết kế aggregate/transaction |
| “Reshard chỉ copy file là xong.” | Write xảy ra khi copy, stale routing | Catch-up, fencing, cutover |
| “Có nhiều data partitions nghĩa mạng partition.” | Hai khái niệm khác nhau | Phân biệt sharding với CAP |
| “Search index là nguồn Order chuẩn.” | Có thể là read model trễ | Dùng authority cho quyết định quan trọng |
| “Chọn shard key xong không cần thay.” | Workload/tenant phân bố thay đổi | Theo dõi và kế hoạch reshard |
| “Cluster healthy nghĩa mọi Order truy cập được.” | Một shard/replica group có thể hỏng | Health theo shard và operation |

## 32. Bài tập vận dụng

### Bài 1 — Phân biệt hai sơ đồ

Sơ đồ A có ba node, mỗi node lưu **toàn bộ** 6 triệu Order. Sơ đồ B có ba node, mỗi node lưu **2 triệu Order khác nhau**.

1. Sơ đồ nào là replication?
2. Sơ đồ nào là sharding?
3. Nếu một node B hỏng và không có replica, tác động là gì?
4. Nếu một node A hỏng, khi nào hai node còn lại có thể tiếp tục?

### Bài 2 — Kết hợp shard và replica

Cluster có **5 logical shards**, RF=3:

- Có bao nhiêu replica placements?
- Nếu mỗi logical shard có 8 GB data+index, tổng dung lượng các bản là bao nhiêu, chưa tính overhead?
- Có bắt buộc dùng 15 physical server không?
- Khi node chết, điều gì quyết định shard còn phục vụ được?

### Bài 3 — Tính dung lượng

Dữ liệu có 12 triệu document, trung bình 2 KB decimal/document, index chiếm thêm 50% document data. Chia thành bốn shard và RF=3.

1. Tổng data logic?
2. Tổng data+index?
3. Dung lượng trung bình mỗi shard?
4. Tổng các bản ở RF=3?
5. Những loại overhead nào chưa tính?

### Bài 4 — Range vs hash

Order mới có `createdAt` luôn tăng. So sánh:

- Range shard theo `createdAt`.
- Hash shard theo `orderId`.

Với mỗi cách, nêu tác động lên write distribution, query 7 ngày gần nhất, point lookup và resharding.

### Bài 5 — Tenant hotspot

Tenant A có 8 triệu Order, ba tenant khác mỗi tenant 50.000 Order. Hệ phân mảnh theo tenantId.

1. Vì sao có thể mất cân bằng?
2. Thêm node có giải quyết hot tenant không nếu tenant không thể tách?
3. Thiết kế bucket theo Order ID cho A.
4. Query liệt kê mọi Order của A tốn thêm gì?

### Bài 6 — Targeted vs scatter–gather

Sharding theo `tenantId`:

~~~text
Q1: tenantId='merchant-a' AND orderId='O900'
Q2: status='PAID' ORDER BY createdAt DESC LIMIT 20
Q3: tenantId='merchant-a' AND shopId='shop-12'
~~~

Query nào có khả năng target một shard hơn? Query nào có thể cần scatter? Index `(shopId,status,createdAt)` có tự thay routing key cho Q2 không?

### Bài 7 — Global uniqueness

Hai shard lưu User khác nhau, mỗi shard có unique index local theo `email`.

1. Vì sao vẫn có thể có cùng email ở hai shard?
2. Đề xuất cơ chế global email reservation.
3. Nếu request bị retry sau timeout, idempotency cần làm gì?
4. Khi chuyển shard, registry mapping cần cập nhật an toàn ra sao?

### Bài 8 — Resharding và ghi trong lúc copy

Owner A đang chuyển tenant sang B:

~~~text
T1: snapshot copy bắt đầu
T2: Order O900 được cập nhật trên A
T3: B trở thành owner
~~~

1. Nếu B chỉ có snapshot tại T1, lỗi gì xảy ra?
2. Catch-up và cutover cần những bước gì?
3. Routing cache stale gây nguy cơ gì?
4. Cần những metric nào để kiểm chứng?

### Bài 9 — Cassandra partition key

Giả sử bảng `orders_by_shop_day` dùng partition key `(tenant_id,shop_id,day_utc)`.

- Query lấy 20 đơn mới nhất của một ngày chạm bao nhiêu logical partitions?
- Query lấy dữ liệu trong một tuần cần xử lý ra sao?
- Nếu partition chỉ theo `tenant_id`, tenant lớn gặp rủi ro gì?
- RF=3 có nghĩa mỗi logical partition nằm trên đúng ba bản theo placement nào? Phần nào phụ thuộc cấu hình engine?

### Bài 10 — DynamoDB hot partition

Một ứng dụng ghi 10.000 Order/s vào cùng một partition key `SHOP#12#TODAY`.

1. Nguy cơ hot key là gì?
2. Thiết kế bốn bucket theo Order ID.
3. Point lookup và query top-20 mới nhất thay đổi thế nào?
4. GSI có giải quyết được mọi hot key không?

### Bài 11 — Elasticsearch primary vs replica

Một index có 6 primary shards và 2 replicas cho mỗi primary.

- Có bao nhiêu shard copies?
- Tăng replica count thêm một tác động trực tiếp lên logical dataset không?
- Tăng số primary shard phục vụ mục tiêu gì?
- Tại sao một query tìm trên toàn index vẫn có bước merge?

### Bài 12 — Redis Cluster

Một Redis Cluster có ba masters, mỗi master sở hữu một số hash slots, mỗi master có một replica.

1. Cái gì quyết định key đi tới master nào?
2. Replica khác master theo cách nào?
3. Khi thêm một master, điều gì phải chuyển?
4. Vì sao hash tags giúp colocate multi-key operation nhưng có thể gây hotspot?

### Bài 13 — Replica và backup

Một người xóa nhầm toàn bộ Order của tenant A; mutation xóa được nhân bản ngay sang các replica.

- RF=3 có cứu được dữ liệu đã bị xóa hợp lệ không?
- Backup PITR/snapshot giúp khác gì?
- Cần thử restore và giữ bản sao ở failure domain nào?

### Bài 14 — Chọn thiết kế cho SaaS

Thiết kế cluster cho một SaaS có 1.000 tenant nhỏ và 3 tenant cực lớn, yêu cầu:

- Point lookup p95 thấp.
- Danh sách Order theo shop trong 7 ngày.
- Một tenant không làm toàn cluster chậm.
- Chịu lỗi một node/AZ.
- Có thể tăng dung lượng theo năm.

Hãy đề xuất shard key, replica policy, routing, read models, resharding và những metric cần theo dõi. Phải giải thích **đánh đổi**, không chỉ nêu tên một database.

## 33. Quy trình ra quyết định sharding và replication

~~~mermaid
flowchart TD
    A["Hệ NoSQL chạm giới hạn hoặc cần chịu lỗi"] --> B{"Mục tiêu chính?"}
    B -->|Dung lượng / write scale / placement| C["Phân tích sharding"]
    B -->|Node failure / data redundancy / read replicas| D["Phân tích replication"]
    C --> E["Chọn shard key theo query và phân bố"]
    E --> F["Đo skew, hotspots, fan-out"]
    D --> G["Chọn RF, failure domains và consistency"]
    F --> H["Kết hợp sharding với replication nếu cần"]
    G --> H
    H --> I["Routing, migration, recovery, backup"]
    I --> J["Benchmark + fault tests + invariant checks"]
    J --> K["Giám sát và điều chỉnh theo workload"]
~~~

Một checklist trước khi triển khai:

1. **Nút thắt thật là gì?** Disk capacity, memory working set, write QPS, read QPS hay network latency?
2. **Tập dữ liệu nào cần phân mảnh?** Collection/table/index/tenant/domain?
3. **Shard key nào phục vụ query chủ đạo?** Có đủ cardinality và phân bố không?
4. **Query nào sẽ fan-out?** Có cần global index hoặc read model khác không?
5. **Có tenant/hot key lớn bất thường không?** Cần bucket hoặc escrow không?
6. **Ranh giới transaction và uniqueness ở đâu?**
7. **Mỗi shard cần bao nhiêu replica?** Replica nằm trên failure domains nào?
8. **Read/write consistency và failover contract là gì?**
9. **Có backup/PITR và restore drill không?**
10. **Khi thêm node, dữ liệu chuyển bằng giao thức nào?** Có catch-up/cutover/fencing không?
11. **Router và client cache metadata có thể stale không?**
12. **Giám sát gì theo shard?** Byte, QPS, p95, hot key, replication lag, errors.
13. **Chi phí tổng có hợp lý không?** Disk × RF, network replication, coordinator, migration.
14. **Phương án có còn hoạt động khi một shard hoặc một AZ không reachable không?**

## Kết luận

**Phân mảnh và tạo bản sao không phải hai từ khác nhau cho cùng một kỹ thuật.**

- **Sharding** chia **những phần dữ liệu logic khác nhau** ra nhiều owner để mở rộng dung lượng và phân phối tải. Đổi lại, nó đưa vào bài toán shard key, routing, hotspot, scatter–gather, distributed transaction và resharding.
- **Replication** tạo **nhiều bản của cùng một phần dữ liệu** để hỗ trợ chịu lỗi, failover, durability và một số workload đọc. Đổi lại, nó tiêu tốn storage/network, có thể xuất hiện replica lag và cần quy tắc consistency/authority.
- **Kết hợp cả hai** có nghĩa mỗi shard quản lý một tập con dữ liệu, rồi tập con đó có nhiều replicas; ví dụ bốn shards với RF=3 tạo 12 replica placements, không đồng nghĩa 12 logical shards hay bắt buộc 12 máy.
- **Nhiều node không bảo đảm scale tuyến tính**: một hot tenant, một hot key, global query hoặc cross-shard transaction có thể giữ nguyên nút thắt.
- **Đúng shard key quan trọng hơn số shard đơn thuần**: thiết kế phải bắt đầu từ truy vấn, data distribution, transaction boundary và hướng tăng trưởng.
- **Chịu lỗi đòi hỏi replication và placement thích hợp; khôi phục dữ liệu bị xóa nhầm còn cần backup**, không thể chỉ dựa vào các shards.
- **Định tuyến là một phần của tính đúng**: cần biết owner hiện tại, chọn replica được phép phục vụ, và xử lý thay đổi mapping khi resharding.

Khi cần mở rộng hệ thống NoSQL, hãy luôn tách hai câu hỏi: **“Phần dữ liệu này nên được đặt trên shard nào để trải tải?”** và **“Shard ấy cần bao nhiêu bản sao, trên những failure domain nào, để giữ hợp đồng dữ liệu khi có lỗi?”**. Trả lời đúng cả hai sẽ tạo ra một kiến trúc vừa mở rộng được, vừa có khả năng vận hành an toàn.
