# Mở rộng hoặc thu hẹp cụm và kiểm soát di chuyển dữ liệu trong MongoDB

## 1. Bài toán vận hành: dữ liệu và lưu lượng tăng nhanh

Một ứng dụng quản lý tin đăng cho thuê nhà ban đầu dùng một MongoDB replica set ba thành viên. Sau một năm, số tin đăng và lịch sử sự kiện tăng nhiều lần:

- Collection **listings** chứa hàng chục triệu document.
- Collection **bookingEvents** tăng liên tục do ghi sự kiện.
- Một tenant lớn tạo phần lớn traffic, đặc biệt vào giờ cao điểm.
- Thời gian phản hồi tìm kiếm **p95/p99** tăng, disk I/O cao.
- Dung lượng trống trên các node giảm, cửa sổ bảo trì và backup kéo dài.

Nhóm vận hành đặt câu hỏi:

> Nên thêm một thành viên vào replica set, nâng cấu hình máy, tạo thêm shard, hay đổi shard key?

Không có câu trả lời chung chỉ dựa vào tổng dung lượng. **Mở rộng cụm** có thể nhằm tăng **tính sẵn sàng, khả năng đọc, năng lực ghi, dung lượng lưu trữ hoặc khả năng phân tán workload**. Mỗi mục tiêu cần thao tác khác nhau.

Giả sử đã triển khai sharded cluster với ba shards, sau đó muốn thu nhỏ xuống hai shards để giảm chi phí. Ta lại gặp bài toán khác:

> Làm sao đưa dữ liệu khỏi shard sắp loại bỏ mà không mất document, không để application đọc sai và không gây quá tải các shard còn lại?

Với MongoDB, cần phân biệt hai nhóm công việc:

1. **Topology scaling:** thay đổi số thành viên replica set, số shards hoặc tài nguyên của chúng.
2. **Data placement/movement:** quản lý việc dữ liệu được phân chia và di chuyển giữa các shards, với tác động lên balancer, mạng, đĩa, cache và tải ứng dụng.

Sơ đồ tổng quan:

~~~text
                      Applications
                           |
                  Driver / mongos
                           |
       +-------------------+-------------------+
       |                                       |
 Replica set (không shard)              Sharded cluster
       |                                       |
   Primary + Secondaries               Shard A  Shard B  Shard C
   (cùng bộ dữ liệu)                        |       |        |
       |                                Replica  Replica  Replica
 Thêm secondary để                        Set     Set      Set
 tăng redundancy/read scale                \       |        /
                                            \      |       /
                                       Balancer / range moves
~~~

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **scale up/down**, **replica-set scale out**, **shard scale out/in** và **resharding**.
2. Giải thích tại sao **thêm secondary không tự chia dữ liệu và write load** của replica set.
3. Hiểu vai trò **mongos, config server replica set, shard replica sets, shard key, chunks/ranges và balancer**.
4. Lập kế hoạch thêm/bớt replica-set member với **initial sync, majority, election và replication lag**.
5. Mô tả quy trình thêm shard, chuẩn bị dữ liệu, giám sát rebalance và xác minh phân bố.
6. Mô tả quy trình remove shard/draining và những trường hợp khó như **unsharded collections, database primary shard và zone constraints**.
7. Nhận diện dữ liệu lệch, hot shard, shard key không phù hợp, jumbo/unsplittable range và chi phí di chuyển.
8. Thiết kế tiêu chí an toàn về **latency, throughput, lỗi, dung lượng, HA, backup/RPO/RTO** trước và sau scaling.
9. Xây runbook có **preflight, giám sát, giới hạn, điểm dừng và hậu kiểm**.
10. Chạy lab mongosh mô phỏng phân bố tải/dữ liệu mà **không thay đổi topology MongoDB thật**.

> **Giới hạn quan trọng:** Những lệnh quản trị replica set/sharding trong bài dùng để giải thích và lập runbook, **không phải một chuỗi lệnh chạy tự động trên production**. Một số commands/helpers và thuật toán cân bằng đã thay đổi theo phiên bản MongoDB; khả năng trên **Atlas** khác self-managed. Mỗi thao tác thật cần kiểm tra tài liệu đúng version, quyền, topology, backup và maintenance plan. Lab an toàn ở cuối bài chỉ thao tác trong database **mongo_scaling_lab_381**.

## 2. Bốn kiểu mở rộng/thu hẹp dễ nhầm

### 2.1. Vertical scaling: scale up/down

**Scale up** là tăng tài nguyên của một node:

- Thêm RAM hoặc tăng WiredTiger cache khả dụng theo cấu hình.
- Tăng CPU.
- Tăng IOPS/throughput hoặc dung lượng storage.
- Nâng class của instance/cloud tier.

**Scale down** là giảm tài nguyên khi tải thấp hơn và vẫn giữ headroom.

Ví dụ:

~~~text
Trước: 8 vCPU, 32 GiB RAM
Sau:  16 vCPU, 64 GiB RAM
~~~

MongoDB không tự cần di chuyển ranges giữa shards chỉ vì tăng CPU. Tuy nhiên, việc đổi máy hoặc storage có thể đòi restart, node replacement hoặc migration ở tầng hạ tầng. Với Atlas, hành vi availability/automation phụ thuộc loại cluster và cấu hình.

**Tăng dung lượng disk không giải quyết mọi latency.** Nếu một index không phù hợp khiến query quét 2 triệu documents, thêm disk capacity không biến query thành index scan.

### 2.2. Horizontal scaling của replica set

Thêm member vào replica set:

~~~text
                 Replica set

        Primary (writes)
             |
          oplog
        /     |      \
  Secondary A B       C (new member)
~~~

Các **data-bearing members** trong cùng replica set lưu bản sao logic của **cùng tập dữ liệu**, không mỗi node một phần collection.

Thêm secondary có thể:

- Tăng mức dự phòng dữ liệu/khả năng chịu lỗi theo thiết kế.
- Tạo nguồn reads nếu ứng dụng sử dụng read preference phù hợp.
- Có node dành cho backup/reporting.

Nhưng **không tự tăng write throughput của một primary bằng cách chia các writes trên nhiều primaries**, và không chia nhỏ storage footprint của mỗi member.

### 2.3. Horizontal scaling bằng sharding

**Sharding** phân bố những **khoảng giá trị shard key** (thường gọi là chunks/ranges) của một collection trên nhiều shards.

~~~text
Sharded collection: bookingEvents

Range R1 ---> Shard A
Range R2 ---> Shard B
Range R3 ---> Shard C
~~~

Mỗi shard thường được triển khai như một **replica set**, cung cấp tính sẵn sàng cho phần dữ liệu mà shard đó sở hữu.

Thêm shard có thể tăng dung lượng tổng và tăng năng lực ghi/đọc khi dữ liệu và requests **được định tuyến đủ phân tán**. Tuy nhiên, việc thêm shard không tự giải quyết **hot shard key** hoặc các truy vấn không target đúng shard.

### 2.4. Resharding

**Resharding** thay đổi cách collection được phân bố theo **shard key khác** bằng cơ chế được phiên bản MongoDB hỗ trợ.

Nó có thể cần khi:

- Shard key hiện tại có cardinality thấp.
- Một tenant/giá trị shard key quá nóng.
- Các truy vấn thường scatter-gather.
- Phân bố tăng trưởng không tương thích với key đang dùng.

Resharding khác thêm shard. **Thêm shard** chỉ bổ sung năng lực placement; **resharding** thay đổi trục phân chia. Không phải mọi imbalance đều sửa được bằng việc thêm máy.

### 2.5. Bảng chọn chiến lược

| Mục tiêu | Hướng thường cân nhắc | Giới hạn |
| --- | --- | --- |
| CPU/memory thiếu trên node | Scale up | Giới hạn máy, chi phí và restart |
| Cần thêm data redundancy | Thêm data-bearing replica member | Không chia ghi/capacity dữ liệu |
| Cần thêm nguồn đọc | Thêm secondary + read routing | Secondary có thể stale, primary vẫn chịu writes |
| Dataset/shard capacity tăng | Thêm shard | Phụ thuộc shard key và data rebalancing |
| Một tenant gây hotspot | Đánh giá shard key/resharding, workload | Thêm shard chưa chắc giải quyết |
| Shard dư capacity, muốn giảm chi phí | Remove shard + draining | Phải đủ tài nguyên và di chuyển an toàn |
| Node dư tài nguyên | Vertical scale down có kiểm soát | Có nguy cơ mất headroom |

## 3. Thành phần của sharded cluster

### 3.1. mongos

**mongos** là query router: nhận các request từ client, dùng metadata sharding để định tuyến đến shard phù hợp.

~~~text
Client/Driver
     |
     v
    mongos
   /  |  \
  A   B   C    (shard replica sets)
~~~

Không coi mongos là node lưu toàn bộ documents. Snapshot một host chỉ chạy mongos **không phải backup dữ liệu của sharded cluster**.

### 3.2. Config server replica set (CSRS)

Config servers lưu **metadata phân bố dữ liệu, các shard và những thông tin cấu hình định tuyến**. Chúng đóng vai trò thiết yếu khi xác định shard nào sở hữu range nào.

Không tự sửa trực tiếp metadata collections trong database **config** để “ép” di chuyển dữ liệu. Các cấu trúc metadata và quy trình quản lý có thể đổi giữa phiên bản.

### 3.3. Shards

Một shard chứa phần dữ liệu của sharded collections và có thể chứa unsharded collections theo mô hình deployment/version.

Thông thường mỗi shard là replica set:

~~~text
Shard A: rsA(primary, secondary, secondary)
Shard B: rsB(primary, secondary, secondary)
Shard C: rsC(primary, secondary, secondary)
~~~

**HA bên trong shard** và **phân tán dữ liệu giữa shards** là hai lớp khác nhau.

### 3.4. Shard key

**Shard key** là một hoặc nhiều fields dùng để phân chia/định tuyến dữ liệu của sharded collection.

Ví dụ:

~~~javascript
{ tenantId: 1, createdAt: 1 }
~~~

hoặc một hashed shard key được deployment hỗ trợ:

~~~javascript
{ listingId: "hashed" }
~~~

Chọn shard key cần xem:

- **Cardinality** (số giá trị khác nhau).
- **Frequency distribution** (giá trị nào xuất hiện nhiều).
- **Monotonicity** (ghi theo thời gian tăng liên tục).
- **Query targeting** (truy vấn có shard key không).
- **Growth/hot tenants**.
- **Zones/data residency**.
- Các quy tắc index/unique constraint và khả năng của version.

### 3.5. Ranges/chunks

MongoDB dùng metadata các **khoảng shard key** để quản lý phân bố. Một số tài liệu/command gọi chúng là **chunks**. Các phiên bản hiện đại cân bằng theo dữ liệu/ranges với những chính sách và thuật toán tùy version.

Ví dụ khái niệm:

~~~text
{ key: MinKey .. 1000 }   -> Shard A
{ key: 1000 .. 2000 }     -> Shard B
{ key: 2000 .. MaxKey }   -> Shard C
~~~

Đừng tự suy luận “mỗi chunk bằng đúng 64 MiB” hoặc “mỗi shard cần có số chunks bằng nhau” cho mọi phiên bản. Chunk/range size và balancing heuristics có thể khác.

### 3.6. Balancer

**Balancer** điều phối di chuyển ranges giữa shards nhằm đáp ứng các quy tắc phân bố của cluster. Khi add shard, nó có thể chuyển một phần dữ liệu để dùng năng lực mới; khi remove shard, quá trình draining cần di chuyển dữ liệu khỏi shard được loại.

Balancer không tự bảo đảm:

- Mỗi shard có đúng số documents như nhau.
- Latency của mọi shard bằng nhau.
- Hot tenant được chia đều.
- Mọi tập dữ liệu không đủ điều kiện split đều có thể chia.

Balancer giải quyết **placement theo metadata và policy**, không phải mọi nút nghẽn ứng dụng.

## 4. Đọc tình trạng hiện tại trước khi quyết định scale

### 4.1. Inventory topology

Cần ghi lại:

- Cluster là standalone, replica set hay sharded.
- MongoDB binary version, **Feature Compatibility Version (FCV)**.
- Số shards và số replica members của từng shard.
- CSRS/mongos topology.
- Roles/votes/priority của members.
- Dung lượng data/index/journal/oplog mỗi node.
- Tốc độ tăng dữ liệu và xóa.
- Mức CPU/RAM, WiredTiger cache, disk IOPS, network.
- Query/read/write mix, write concern/read preference.
- Backup status, RPO/RTO, restore drill gần nhất.

### 4.2. Lệnh xem replica set

Khi đang kết nối tới một **mongod thuộc replica set**, dùng account có quyền phù hợp:

~~~javascript
printjson(rs.status());
printjson(rs.conf());
~~~

Đây là **read-only inspection**. Khi kết nối qua mongos, các helpers replica-set trực tiếp không nhằm lấy status của từng shard. Để xem một shard member cần kết nối đến deployment/member phù hợp với policy.

### 4.3. Lệnh xem sharded cluster

Khi kết nối qua **mongos**:

~~~javascript
sh.status();

printjson(
  db.getSiblingDB("admin").runCommand({
    listShards: 1
  })
);
~~~

Trong các phiên bản mongosh hỗ trợ, có thể tham khảo:

~~~javascript
printjson(sh.getBalancerState());
~~~

Những helpers/admin commands này yêu cầu quyền và feature support tương ứng. Output của **sh.status()** có thể rất dài; tránh lưu nguyên metadata nhạy cảm vào log công khai.

### 4.4. Nhìn đúng triệu chứng

| Quan sát | Khả năng | Điều cần xác minh |
| --- | --- | --- |
| Cả cluster CPU cao | Workload chung, query plan, thiếu compute | Per-shard CPU, explain, throughput |
| Chỉ một shard CPU cao | Hot shard/tenant, skew hoặc routing | Shard key/query mix, per-shard ops |
| Disk một shard gần đầy | Data skew, indexes, orphan/temporary data | Data/index sizes, ranges, cleanup |
| Secondary lag tăng | Quá tải disk/network, initial sync/migration | Applied optime, oplog window |
| p99 tăng khi balancer chạy | Migration cạnh tranh resource | Migration progress, disk/network, slow ops |
| Scatter-gather tăng | Query thiếu shard key phù hợp | Explain/shard targeting |
| App pool timeout | Pool/network, không nhất thiết shard capacity | Driver checkout wait, server metrics |

Không quyết định addShard chỉ từ một biểu đồ CPU trung bình toàn cluster.

## 5. Capacity planning trước khi thêm hoặc bớt shard

### 5.1. Chỉ tính data size là chưa đủ

Một shard dùng storage cho:

- Collection data.
- Indexes.
- WiredTiger internal/temporary data.
- Oplog và journal.
- Migration staging/cleanup theo cơ chế.
- Backup/index build/maintenance overhead.

Ngoài bytes hiện tại, cần **headroom** cho tăng trưởng và di chuyển dữ liệu. Khi shrink, data trên shard bị loại phải đi vào những shards còn lại mà vẫn giữ khoảng trống vận hành.

### 5.2. Bài toán thêm shard

Giả sử ba shards đang chứa tổng **2,4 TB** data/index cần phân bố tương đối đều. Nếu thêm shard thứ tư và mục tiêu lý tưởng là bốn shards mỗi shard **0,6 TB**, khoảng **0,6 TB** dữ liệu cần tới shard mới.

Đây chỉ là **ước lượng lý tưởng về dung lượng đích**:

~~~text
Trước:
  Shard A: 0,8 TB
  Shard B: 0,8 TB
  Shard C: 0,8 TB

Sau (mục tiêu minh họa):
  Shard A: 0,6 TB
  Shard B: 0,6 TB
  Shard C: 0,6 TB
  Shard D: 0,6 TB
~~~

Không phải cứ thêm shard là balancer đảm bảo phân bố 0,6 TB chính xác. Zones, shard key, kích thước ranges, collections và balancing policies có thể khiến phân bố thực khác.

### 5.3. Ước lượng thời gian di chuyển

Nếu cần chuyển khoảng **600 GB** và throughput hữu ích trung bình là **50 MB/s** (cùng quy ước GB/MB thập phân):

\[
\text{Thời gian lý tưởng} \approx
\frac{600{,}000\ \text{MB}}{50\ \text{MB/s}}
=12{,}000\ \text{s}
\approx 3\ \text{giờ}\ 20\ \text{phút}
\]

Thời gian thực có thể dài hơn nhiều do:

- Ứng dụng tiếp tục ghi.
- Throttle/giới hạn migrations.
- Network giữa shard replica sets.
- Index/copy/catch-up/cleanup overhead.
- Các ranges không thể chia đơn giản.
- Balancer window và zones.
- CPU/disk đang phục vụ traffic.

Không lập SLA dựa trên công thức lý tưởng mà chưa thử trên môi trường đại diện.

### 5.4. Bài toán bớt shard

Nếu bốn shards mỗi shard lưu 600 GB và muốn còn ba shards, phải có chỗ chứa ít nhất 600 GB dữ liệu được drain, ngoài headroom. Mỗi shard còn lại có thể tiến tới khoảng 800 GB, chưa kể index/temp/replication overhead.

Nếu disk mỗi shard chỉ còn 100 GB trống, thao tác shrink **không an toàn** chỉ vì tổng data theo logic “nhỏ hơn tổng dung lượng danh định”.

### 5.5. Quy tắc headroom

Không có một tỷ lệ trống 10%, 20% hay 30% đúng cho mọi workload. Chọn headroom bằng:

- Độ lớn và tốc độ tăng data/index.
- Peak write rate.
- Disk latency/tier.
- Yêu cầu migration cleanup.
- Backup/index build workload.
- Thời gian để provision thêm capacity.
- RPO/RTO và safety margin theo policy nội bộ.

### 5.6. Tốc độ quan trọng hơn số shard

Ví dụ shard A CPU 90%, shard B và C CPU 30%. Nếu hot writes luôn target một shard key value ở A, thêm D chưa chắc làm giảm CPU A. Cần xác định **có thể phân tán key và queries** sang D hay không.

## 6. Thêm một replica-set member: mở rộng tính sẵn sàng, không chia shard

### 6.1. Quy trình logic

~~~text
Preflight:
  health + quorum + backups + oplog window
       |
Provision mongod mới
       |
Network/TLS/internal auth/version/storage
       |
Add member
       |
Initial sync / data copy / oplog catch-up
       |
Member trở thành SECONDARY đủ điều kiện
       |
Kiểm tra replication và read routing
       |
Đánh giá role/priority/votes theo HA policy
~~~

### 6.2. Initial sync

Khi thêm data-bearing member, member mới thường cần **initial sync** để tạo bản sao dữ liệu và bắt kịp những operations xảy ra trong quá trình copy. Thời gian phụ thuộc:

- Data size và index build.
- Độ nhanh của sync source/target.
- Network và disk throughput.
- Replication lag và oplog window.
- Ảnh hưởng của workload hiện tại.

Initial sync có thể tạo **đọc và truyền dữ liệu rất lớn**, nên một thao tác “chỉ thêm secondary” vẫn có tác động performance.

### 6.3. Ví dụ rs.add để hiểu cú pháp

Trên **PRIMARY** của một replica set trong **lab**, với account quản trị phù hợp, ví dụ minh họa:

~~~javascript
// MINH HỌA QUẢN TRỊ - KHÔNG chạy trên production vô kế hoạch.
// Host phải là mongod mới đã provision và có internal auth/TLS.
rs.add({
  host: "mongo-new.lab.example:27017",
  priority: 0,
  votes: 0
});
~~~

Trong nhiều trường hợp, thêm trước dưới dạng **non-voting, non-electable** có thể giúp kiểm soát ảnh hưởng quorum/elections khi initial sync. Sau khi member bắt kịp và có đánh giá HA, việc thay đổi votes/priority cần quy trình riêng, đặc biệt nếu đang ở giới hạn voting members hoặc topology có các constraints khác.

**Không** tự thêm một member bằng hostname placeholder. Cú pháp, votes/priority/requirements cần xác minh theo phiên bản và replica configuration.

### 6.4. Theo dõi member mới

~~~javascript
const status = rs.status();
printjson(status.members.map(m => ({
  name: m.name,
  stateStr: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate
})));
~~~

Các field output cụ thể có thể thay đổi theo version. Không coi một member đã hiển thị trong configuration là nó đã **hoàn tất initial sync** và an toàn để nhận reads/đóng góp HA.

### 6.5. Read preference

Nếu muốn dùng secondary cho read scaling, ứng dụng cần có **read preference** thích hợp và hiểu trade-off:

- Primary vẫn là nơi xử lý writes của replica set.
- Secondary reads có thể **stale** so với primary.
- Query targeting/replica topology ảnh hưởng latency.
- Secondary dành cho backup có thể không nên phục vụ user queries.

Thêm node mà toàn ứng dụng vẫn dùng **primary** sẽ không tự dời read workload sang secondary.

### 6.6. Majority và voting

Thay đổi số **voting members** có thể làm thay đổi majority quorum, khả năng election và việc ACK writeConcern majority. Không chỉ đếm số máy vật lý. Phải xét:

- Members có votes hay không.
- Khả năng election của members.
- Failure domains.
- Network partitions.
- Write concern và journaling policy.

Một **arbiter** tham gia voting nhưng **không lưu dữ liệu**, nên không tăng read capacity hoặc nơi sao lưu. Không thêm arbiter để giải quyết thiếu disk hoặc tăng write throughput.

## 7. Bớt replica-set member: ưu tiên quorum và khôi phục

### 7.1. Tình huống

Replica set có bốn data-bearing members, một node cũ cần loại do thay máy. Việc loại member có thể phù hợp sau khi node mới đã synced và HA vẫn đáp ứng chính sách.

### 7.2. Runbook trước khi remove

1. Xác minh backup và đường restore.
2. Xem **rs.conf()** và **rs.status()**.
3. Xem votes, priority, hidden, delayed và ảnh hưởng tới quorum.
4. Xác định member không còn phục vụ backup/read traffic.
5. Xác định mức failure tolerance sau khi remove.
6. Xác minh app/monitoring/DNS không phụ thuộc node đó.
7. Chọn maintenance window nếu cần.

### 7.3. Cú pháp minh họa

Trên PRIMARY, có quyền quản trị và sau khi đã xác minh điều kiện:

~~~javascript
// CHỈ MINH HỌA CÁCH GỌI, không chạy trên cluster thật.
rs.remove("mongo-old.lab.example:27017");
~~~

**rs.remove() thay đổi replica-set membership, không drain một shard của sharded cluster.** Nó cũng không phải thao tác cân bằng data ranges. Nếu member là shard primary hoặc voting member quan trọng, cần thêm bước chuẩn bị khác; không dùng lệnh này như cách “giảm 1 shard”.

### 7.4. Hậu kiểm

- Replica set vẫn có PRIMARY ổn định.
- Majority write concern hoạt động đúng.
- Các SECONDARY healthy và lag trong ngưỡng.
- Read preference không chọn node cũ.
- Backups/monitoring hợp lệ.
- Tổng throughput và p95/p99 trong SLO.

### 7.5. Không xóa dữ liệu trên disk ngay

Việc dừng/loại một mongod có thể là một phần của thay máy, nhưng disk cũ chứa dữ liệu nhạy cảm. Cần retention/security disposal policy, không tự xóa nóng hoặc mount lại vào member đang hoạt động. Chỉ decommission tài nguyên khi đã có approval, dữ liệu và secrets được xử lý đúng.

## 8. Thêm shard: quá trình gồm cả provisioning và rebalance

### 8.1. Điều kiện ban đầu

Trước khi add shard, kiểm tra:

- Mongos và CSRS khỏe mạnh.
- Mỗi shard replica set ổn định.
- Shard mới là replica set phù hợp, đã được cấu hình và không thuộc cluster khác.
- Version/FCV/feature compatibility phù hợp.
- Network, hostname resolution, TLS/internal authentication và quyền quản trị đúng.
- Disk/index/IOPS capacity trên shard mới.
- Backup và monitoring bao phủ shard mới.
- Zone/data placement rules được xét.
- Balancer và migrations có phương án giám sát.

### 8.2. Cú pháp minh họa addShard

Chỉ thực hiện khi đã có mongos của **lab sharded cluster** và replica set mới được provision:

~~~javascript
// Kết nối đến mongos, không phải mongod standalone.
// Đây là ví dụ minh họa vận hành.
sh.addShard(
  "rsShardD/shard-d1.lab.example:27017,shard-d2.lab.example:27017,shard-d3.lab.example:27017"
);
~~~

Hoặc command admin tương đương nếu deployment hỗ trợ:

~~~javascript
db.getSiblingDB("admin").runCommand({
  addShard:
    "rsShardD/shard-d1.lab.example:27017,shard-d2.lab.example:27017,shard-d3.lab.example:27017"
});
~~~

Đây **không phải bước của lab dữ liệu mongosh ở cuối bài**. Không có những hosts này trên máy người học; không chạy với tên server thật nếu chưa có quy trình change management.

### 8.3. Sau khi addShard thành công

Thêm shard vào metadata cluster chưa chứng minh dữ liệu đã được phân bố. Cần:

1. Xác minh shard xuất hiện trong **listShards/sh.status()**.
2. Xác minh nó healthy.
3. Theo dõi balancing và migration.
4. Xem phân bố thực theo collection/shard.
5. Theo dõi latency/throughput/error rate ứng dụng.
6. Đảm bảo backup, failover/monitoring bao phủ shard mới.

### 8.4. Balancer không có nhiệm vụ chuyển mọi collection ngay

Balancer hoạt động dựa trên điều kiện cần cân bằng, giới hạn migration và placement constraints. Có thể:

- Những collections vẫn tập trung ở shard cũ trong một thời gian.
- Zones hạn chế nơi dữ liệu được phép đặt.
- Shard key làm một số ranges khó chia.
- Unsharded collections có placement rules riêng.

Đừng chỉ nhìn số shard tăng từ 3 lên 4 rồi tuyên bố write capacity tăng 33%.

## 9. Range migration diễn ra như thế nào?

### 9.1. Các khái niệm donor/recipient

**Donor shard** đang sở hữu range, **recipient shard** sẽ nhận range đó.

~~~text
Shard A (donor)                     Shard D (recipient)
    |                                      |
    |  Range [K1,K2)                       |
    +--------------- copy ---------------->|
    |                                      |
    |  Ghi mới/thay đổi tiếp tục            |
    +--------- catch-up changes ---------->|
    |                                      |
    +----------- ownership commit -------->|
    |                                      |
    |       Metadata/routing cập nhật       |
    |                                      |
    +--- cleanup orphaned data (khi an toàn)
~~~

Đây là mô hình ở cấp ý tưởng. Các giai đoạn chi tiết, thời gian critical section và cách xử lý concurrent writes/transactions phụ thuộc phiên bản MongoDB.

### 9.2. Tại sao migration có thể chậm?

- Range có nhiều bytes.
- Indexes lớn.
- Recipient disk/network chậm.
- Donor chịu write throughput cao và cần catch up.
- Transaction dài hoặc xung đột operation.
- Balancer policy/throttle.
- Zone constraints.
- Metadata/DDL changes.
- Cleanup của dữ liệu cũ và các cursor còn mở.

Tốc độ migration không bằng tốc độ copy một file bằng network tool, vì hệ thống cần bảo vệ **tính nhất quán và định tuyến**.

### 9.3. Routing trong lúc di chuyển

Mongos/driver sử dụng metadata để target shard. Khi ownership đổi, routing cache có thể cần refresh; hệ thống có thể gặp những lỗi tạm thời/retryable conditions theo tính năng/version.

Ứng dụng nên:

- Dùng driver tương thích và supported retry semantics.
- Định nghĩa timeout hợp lý.
- Xử lý network/server transient errors đúng.
- Bảo đảm idempotency ở write workflows khi retry có unknown outcome.
- Theo dõi lỗi và latency tăng trong migration.

Không tắt toàn bộ retry hoặc tự retry không giới hạn mọi write chỉ vì đang rebalance.

### 9.4. Critical section không có nghĩa dừng cả cluster hàng giờ

Range migration được thiết kế để tiếp tục phục vụ workload ở mức phù hợp, với giai đoạn commit/ownership coordination cần giới hạn/đồng bộ. Tuy nhiên, độ trễ cụ thể và các thao tác bị chặn trong từng thời điểm phụ thuộc version và workload.

**Không hứa “migration luôn zero downtime, zero latency impact”.** Phải đo trên môi trường đại diện và có runbook dừng khi SLO bị vi phạm.

### 9.5. Orphan cleanup

Sau khi quyền sở hữu range chuyển, donor có thể còn dữ liệu tạm/orphaned trong lúc cleanup an toàn. Vì thế:

- Dung lượng disk của donor **không nhất thiết giảm tức thì**.
- Thống kê logical data và physical bytes có thể tạm khác.
- Không xóa thủ công “orphan documents” bằng một script tự viết.
- Theo dõi cleanup/retention theo công cụ được hỗ trợ.

### 9.6. Không move bằng updateOne

Với sharded collection, sửa một field shard key không phải phương pháp tổng quát để “di chuyển chunk”. Các thao tác cập nhật shard key có ràng buộc riêng, khác hoàn toàn **range migration** do MongoDB quản lý.

Không làm:

~~~javascript
db.listings.updateMany(
  { tenantId: "t001" },
  { $set: { shardLocation: "shardD" } }
);
~~~

rồi tuyên bố dữ liệu đã được chuyển tới shard D. Một field business tên **shardLocation** không phải routing metadata của MongoDB.

## 10. Balancer: điều khiển ở mức chính sách

### 10.1. Theo dõi trạng thái

Trên mongos, quyền phù hợp:

~~~javascript
sh.status();
printjson(sh.getBalancerState());
~~~

Trong deployment/version hỗ trợ, có thể xem trạng thái cụ thể bằng MongoDB monitoring/admin APIs. Tên fields/output có thể khác giữa các phiên bản.

### 10.2. Khi nào nên quan sát thay vì can thiệp?

Nếu balancer đang chuyển dữ liệu đều, p95/p99 và replication ổn, disk đủ headroom, có thể để quá trình tiếp diễn.

Nếu một migration gây overload:

1. Thu thập evidence của latency, lỗi, disk/network và migrations đang hoạt động.
2. Xác định nguyên nhân có phải migration không.
3. Xem khả năng điều chỉnh migration concurrency/window theo version.
4. Cân nhắc pause balancer có kế hoạch nếu cần.
5. Không dùng thao tác force vô căn cứ.

### 10.3. stopBalancer/startBalancer

Trong những bản mongosh hỗ trợ:

~~~javascript
// MINH HỌA QUẢN TRỊ; KHÔNG chạy tùy tiện.
sh.stopBalancer();

// Sau khi xử lý sự cố và được phép tiếp tục:
sh.startBalancer();
~~~

Việc dừng balancer:

- **Không tự hoàn nguyên** dữ liệu đã di chuyển.
- Có thể trì hoãn draining/rebalance.
- Không đảm bảo một migration đang ở critical phase dừng ngay tại thời điểm gọi.
- Có thể làm chậm các công việc phụ thuộc balancing.

Trước khi đổi trạng thái balancer, cần biết ai/luồng nào đang phụ thuộc và có kế hoạch bật lại.

### 10.4. Manual chunk/range move

MongoDB có các helpers/commands cho di chuyển range/chunk trong những phiên bản phù hợp. Không nên dùng thủ công để “chuyển cho nhanh” khi không hiểu:

- Range boundaries.
- Current owner.
- Shard key pattern.
- Balancer/zone constraints.
- Migration conflicts.
- Target disk headroom.

Bài này cố ý **không đưa một lệnh moveChunk/moveRange chạy trực tiếp lên cluster thật** làm bước lab. Khi cần thao tác vận hành, tham khảo tài liệu đúng MongoDB version và chạy trong change procedure được phê duyệt.

### 10.5. Đơn vị cân bằng không chỉ là số document

Hai ranges có cùng 10.000 documents nhưng kích thước khác nhau nhiều lần nếu một bên chứa arrays lớn và nhiều index entries. Cũng vậy, 10 GB dữ liệu “lạnh” không có chi phí như 10 GB dữ liệu bị truy cập mỗi request.

Theo dõi **bytes, operations, latency và phân bố hot keys** thay vì chỉ đếm documents.

## 11. Thu hẹp sharded cluster: remove shard cần draining

### 11.1. Sai lầm nguy hiểm

Sai:

~~~text
Cluster có 4 shards.
Chọn shard D ít data nhất.
Shutdown mongod của shard D.
Xóa instance/cloud volume.
~~~

Nếu D còn sở hữu ranges hoặc unsharded collections, mongos có thể vẫn route các request tới D. Việc tắt máy không làm MongoDB tự chuyển toàn bộ dữ liệu sang ba shards còn lại.

### 11.2. Draining

**Remove shard** trong sharded cluster là một quy trình đưa dữ liệu và ownership khỏi shard trước khi loại nó khỏi cluster.

~~~text
Preflight capacity/quorum/backup
               |
               v
          Begin drain
               |
               v
Balancer di chuyển ranges sang các shards còn lại
               |
               v
Xử lý unsharded collections / database primary
               |
               v
Theo dõi trạng thái drain và còn dữ liệu gì
               |
               v
MongoDB xác nhận removal completed
               |
               v
Decommission hosts, volumes, monitoring, secrets
~~~

### 11.3. Cú pháp minh họa removeShard

Trên **mongos** của một **sharded lab** đã được phê duyệt:

~~~javascript
// KHÔNG chạy trên production nếu chưa có runbook.
const admin = db.getSiblingDB("admin");
printjson(admin.runCommand({
  removeShard: "shardD"
}));
~~~

Lệnh có thể trả trạng thái **started/ongoing/completed** hoặc các thông tin tiến trình theo phiên bản. Removal có thể kéo dài hàng giờ hoặc lâu hơn; không coi một response bắt đầu thành công là shard đã được gỡ an toàn.

Khi cần truy vấn tiến độ, dùng các commands/monitoring APIs của phiên bản đang chạy. Một số workflows kiểm tra trạng thái bằng lệnh removeShard tiếp theo theo tài liệu, nhưng phải biết semantics version trước khi automation.

### 11.4. Không xóa host trước khi completed

Ngay cả khi dashboards cho thấy dung lượng gần zero, cần xác minh **MongoDB đã hoàn tất thủ tục loại shard** và không còn placement/metadata dependency.

Một shard có thể còn:

- Unsharded collections.
- Vai trò primary shard của database.
- Ranges thuộc zones đặc biệt.
- Dữ liệu đang cleanup hoặc migration chưa commit.
- Những dependencies về backup/monitoring/app access.

### 11.5. Unsharded collections và primary shard

Trong các phiên bản MongoDB, unsharded collections và **primary shard của database** có quy tắc placement/di chuyển riêng. Lệnh có thể liên quan đến **movePrimary**, **moveCollection** hoặc cơ chế mới hơn tùy version.

Không tự chạy các lệnh này theo một công thức duy nhất:

- Kiểm tra database/collections nào chưa sharded.
- Kiểm tra shard đang làm database primary.
- Xác định lệnh hỗ trợ chuyển đúng metadata và dữ liệu.
- Xác minh indexes, quyền, application assumptions.
- Theo dõi quá trình và xác nhận không còn blockers.

### 11.6. Vấn đề zone

Nếu shard D là **shard duy nhất** thuộc zone Z, trong khi một số ranges bắt buộc ở Z, balancer có thể không có đích hợp lệ để drain.

Trước khi remove:

1. Kiểm kê zone-to-shard assignments.
2. Xem zone ranges và data residency requirements.
3. Bảo đảm có đủ shard đích đáp ứng policy.
4. Không tháo zone constraints chỉ để di chuyển dữ liệu sang region bị cấm.

### 11.7. Decommission cuối cùng

Sau khi MongoDB xác nhận completed và sau kiểm tra HA/backup/SLO:

- Loại shard hosts khỏi service discovery/monitoring đúng cách.
- Thu hồi/rotate credentials hoặc certificates của máy cũ.
- Lưu audit/manifest thay đổi.
- Xử lý volumes và data sanitization theo policy.
- Cập nhật disaster recovery topology.
- Cập nhật capacity/cost forecast.

## 12. Shard key quyết định một phần lớn khả năng scale

### 12.1. Cardinality thấp

Shard key:

~~~javascript
{ status: 1 }
~~~

với status chỉ có active/inactive rất ít giá trị. Một key có quá ít giá trị có thể khiến khó chia dữ liệu đủ nhỏ và phân bố đều, tùy schema và range splitting constraints.

Không chọn shard key chỉ vì field xuất hiện nhiều trong query.

### 12.2. Monotonically increasing key

Shard key theo createdAt tăng liên tục có thể khiến writes mới dồn về range chứa giá trị lớn nhất, tạo **hot shard** nếu không có thiết kế phân tán phù hợp.

~~~text
Timeline:
  10:00 -> 10:01 -> 10:02 -> 10:03 ...
                           ^
                     Hot insert tail
~~~

Thêm shard chưa chắc giảm hot spot nếu tất cả writes mới vẫn target một range.

### 12.3. Hashed shard key

Hashed key có thể giúp phân bố giá trị đa dạng khi document keys có cardinality lớn. Nhưng:

- Hashing có trade-off với range queries.
- Hashing **một field có cùng giá trị cho mọi document của tenant lớn** không tự tạo nhiều giá trị hash cho tenant đó.
- Một hot tenant vẫn có thể tập trung nếu shard key không đủ khả năng phân chia bên trong tenant.

Ví dụ nếu toàn bộ document tenant t001 có:

~~~javascript
tenantId: "t001"
~~~

thì shard key chỉ là **{ tenantId: "hashed" }** vẫn hash cùng một giá trị tenantId thành cùng hash key. Đây **không phải** cơ chế tự chia một tenant nóng thành nhiều shards.

### 12.4. Compound shard key

Một compound shard key có thể kết hợp tenant và trường có cardinality cao để cho phép phân chia dữ liệu hợp lý hơn, nhưng phải đánh giá:

- Query targeting theo prefix key.
- Read/write distribution.
- Index requirements.
- Các tenants cực lớn.
- Ranges và zones.
- Semantics unique indexes.

Ví dụ thiết kế cần thử nghiệm:

~~~javascript
{ tenantId: 1, listingId: 1 }
~~~

Không mặc định key này tối ưu cho mọi trường hợp. Nếu listingId được cấp tăng dần theo tenant, nó vẫn có thể có hot tail trong từng tenant. Cần mô phỏng access patterns thực tế.

### 12.5. Scatter-gather

Một query thiếu shard key có thể phải gửi tới nhiều shards:

~~~text
Client -> mongos -> A + B + C + D
                          |
                      Merge results
~~~

Thêm shard làm dữ liệu phân tán nhưng query không target được có thể khiến chi phí scatter-gather tăng. Đo **targeted vs scatter-gather query ratio** khi quyết định shard key.

### 12.6. Resharding khi không thể sửa bằng rebalance

Nếu hotspot xuất phát từ cấu trúc shard key, thêm shards và chạy balancer không đảm bảo sửa được. Cần cân nhắc **reshardCollection**, refine shard key hoặc mô hình dữ liệu khác theo khả năng server.

Resharding có thể tốn nhiều storage/network, tạo dữ liệu tạm và cần theo dõi writes/DDL conflicts. Phải có:

- Backup và restore plan.
- Preflight capacity.
- Query/index compatibility review.
- Giám sát tiến độ.
- Kế hoạch ứng phó failures.
- Post-reshard validation.

Không coi đổi shard key là sửa một dòng config đơn giản.

## 13. Jumbo/unsplittable ranges và dữ liệu lệch

### 13.1. Tại sao range khó chia?

Ví dụ nhiều documents có cùng shard key value hoặc một số documents quá lớn khiến range rất khó/không thể split thành những ranges thỏa điều kiện mong muốn.

Các phiên bản MongoDB có cơ chế và thuật ngữ khác nhau cho **jumbo** hoặc **unsplittable** ranges; không giả định mọi bản dùng chung một marker/trạng thái.

### 13.2. Triệu chứng

- Shard A giữ nhiều data hơn.
- Balancer chạy nhưng di chuyển ít.
- Một số migrations thất bại lặp lại.
- Logs báo range/chunk có vấn đề về split/move.
- Data skew không giảm dù có shard mới.

### 13.3. Cách phân tích

1. Kiểm tra shard key cardinality và frequency.
2. Kiểm tra distribution theo shard/collection.
3. Xem migration logs và balancer status.
4. Xem zone constraints.
5. Kiểm tra document size / hot key distribution.
6. Xác minh version-specific behavior.

Không sửa config metadata hoặc chạy force move một range lớn trên production mà chưa có runbook/version-specific guidance.

### 13.4. Cân bằng bytes không đồng nghĩa cân bằng heat

~~~text
Shard A: 400 GB, 8.000 ops/s
Shard B: 400 GB, 1.000 ops/s
Shard C: 400 GB, 1.000 ops/s
~~~

Data balance về bytes trông tốt nhưng A vẫn là hot shard. Cần điều tra key/query routing, cache, per-shard network/CPU và khả năng phân tán request.

## 14. Zones và data residency

### 14.1. Zone-aware placement

Một tổ chức có thể yêu cầu dữ liệu thuộc khu vực địa lý nhất định chỉ nằm trên shards ở khu vực đó.

~~~text
Zone VN:
  Shard A, B

Zone SG:
  Shard C, D

Data range thuộc VN -> chỉ đến shards được phép ở zone VN
~~~

Đây là ví dụ khái niệm; quy tắc zones còn phụ thuộc shard key/ranges và cấu hình thực.

### 14.2. Thêm shard vào zone

Thêm shard D vào cluster chưa tự làm nó đích hợp lệ cho mọi ranges. Nếu zones đang hạn chế placement, cần cập nhật zone membership/ranges đúng policy. Không tự ý di chuyển dữ liệu xuyên region nếu policy cấm.

### 14.3. Shrink theo zone

Nếu xóa một shard khỏi zone mà không còn đích có capacity đủ, draining có thể bị chặn hoặc dẫn tới hotspot. Phải kiểm tra **capacity theo zone**, không chỉ capacity tổng cluster.

### 14.4. Residency và security

Balancing có thể là hành động vận chuyển dữ liệu qua mạng giữa shards. Cần xem:

- Kết nối mã hóa/TLS.
- Data residency restrictions.
- Network routes và firewalls.
- Key management.
- Audit của thay đổi zone/topology.

## 15. Chọn read/write policies khi scale

### 15.1. Read concern và read preference

Khi thêm secondary hoặc shard:

- Read preference quyết định driver đọc primary/secondary nào trong replica set phù hợp.
- Read concern quyết định guarantee/visibility theo cấu hình.
- Query targeting quyết định request đi tới shard nào.

Không gọi “read from secondary” là một cơ chế chia writes giữa shards.

### 15.2. Write concern

Trên replica set, writeConcern: { w: "majority" } có thể tăng độ bảo đảm replication/durability theo deployment, nhưng latency phụ thuộc health/lag.

Khi mở rộng member hoặc di chuyển data:

- Không tự giảm write concern để benchmark trông nhanh hơn.
- Đo write concern timeouts.
- Kiểm tra majority vẫn có ý nghĩa đúng.
- Xem replica set availability khi đổi voting members.

### 15.3. Transactions nhiều shards

Nếu transaction chạm nhiều shards, overhead coordination có thể cao hơn transaction chỉ một shard/collection phù hợp. Shard key/query design ảnh hưởng số shards tham gia.

Khi scale:

- Đo transaction p95/p99.
- Xem retries/transient errors.
- Tránh hot shard làm tăng chi phí coordination.
- Không giả định shard count càng nhiều thì mọi transaction càng nhanh.

### 15.4. Causal consistency và indexing

Data migration ở tầng shard khác với bảo đảm client đọc lại write và index freshness. Các yêu cầu ứng dụng vẫn cần session/read concern/write concern phù hợp. Không bỏ causal consistency hoặc isolation policy chỉ vì chuyển cluster.

## 16. Giám sát migration: telemetry tối thiểu

### 16.1. Application SLIs

- RPS và successful throughput.
- Error/timeout rate theo query/operation.
- p50/p95/p99.
- Write concern timeouts và retries.
- Transaction latency.
- Read-after-write issues/consistency errors.

### 16.2. MongoDB SLIs

- Per-shard CPU/memory.
- WiredTiger cache/eviction.
- Disk read/write latency, IOPS, free bytes.
- Network in/out giữa shards.
- Connection counts/pool pressure.
- Replication lag và oplog window.
- Read/write operations per shard.
- Balancer/migration statuses, completed/failed migrations.
- Distribution theo shard, collection và zone.

### 16.3. Nhìn cả donor và recipient

Chỉ theo dõi recipient có thể bỏ sót donor bị nghẽn disk/network hoặc oplog lag. Di chuyển range là workload cả hai đầu, còn config servers/mongos có chi phí metadata/routing.

### 16.4. Dung lượng không giảm tức thì

Sau khi chuyển range, donor có thể chờ cleanup nên disk chưa giải phóng ngay. Trong lúc migration, recipient có thể cần đủ chỗ cho dữ liệu mới và temporary overhead.

Không đưa thêm dữ liệu lên recipient chỉ vì thấy bytes used hiện tại chưa tăng nhiều.

### 16.5. Đừng chỉ đo số migration completed

100 migrations hoàn tất không nói:

- Tổng bytes đã chuyển bao nhiêu.
- Còn bao nhiêu ranges/chunks theo policy.
- Có hot shard nào vẫn quá tải.
- Failed/retried migrations mất bao lâu.
- Latency ứng dụng có vượt SLO.

Đặt **progress + health + business SLO** trong cùng dashboard.

## 17. Đặt điều kiện an toàn khi thay đổi topology

### 17.1. Ví dụ guardrails

Một kịch bản tự đặt có thể dùng:

| Chỉ số | Mục tiêu ví dụ | Khi vượt |
| --- | --- | --- |
| Search p95 | ≤ 180 ms | Kiểm tra migration/resource |
| Search p99 | ≤ 450 ms | Cân nhắc pause/reduce migration |
| 5xx/timeout | ≤ 0,5% | Điều tra ngay |
| Replication lag | Trong ngưỡng RPO/HA nội bộ | Giảm tải/chờ member bắt kịp |
| Disk free | Trên mức headroom đã phê duyệt | Dừng scale-in và tăng capacity |
| Oplog window | Đủ cho catch-up và incident margin | Không giữ backup node lag kéo dài |
| Backup age | Không vượt policy | Khôi phục backup coverage |

Các số p95/p99/error là **ngưỡng minh họa**, không phải chuẩn MongoDB. Mỗi nhóm phải chọn từ SLO, RPO/RTO và workload thật.

### 17.2. Stop conditions phải có trước khi làm

Không đợi tới khi node quá tải mới bàn xem có được dừng balancer không. Preflight phải có:

1. Owner ra quyết định pause/hủy.
2. Alert thresholds.
3. Quyền thao tác tương ứng.
4. Các bước an toàn để pause migration theo phiên bản.
5. Kế hoạch khôi phục app traffic.
6. Kế hoạch xử lý dữ liệu đã di chuyển.
7. Cách xác minh trạng thái sau pause.

### 17.3. Không gọi rollback là một nút bấm

Đã chuyển hàng trăm ranges từ A sang D không có nghĩa có thể “rollback tức thì” bằng cách xóa D.

Một **rollback topology change** có thể phải:

- Dừng các migrations mới có kiểm soát.
- Phục hồi tài nguyên hoặc routing.
- Chuyển lại dữ liệu bằng quy trình được hỗ trợ.
- Kiểm tra health và consistency.
- Chọn giữ shard mới tạm thời thay vì gỡ vội.

Nếu đang remove shard, việc thay đổi quyết định giữa chừng có semantics riêng; không giả định có nút **cancel removeShard** ở mọi phiên bản.

### 17.4. Backup không thay thế kế hoạch pause

Backup là phương án phục hồi khi thảm họa, nhưng restore có thể mất nhiều giờ và gây RPO gap. Một sai lệch data distribution nhỏ nên được xử lý bằng tooling/operational procedure phù hợp, không restore toàn cluster theo phản xạ.

## 18. Runbook ADD SHARD chi tiết

### 18.1. Phase A — Planning

~~~text
Goal:
  Tăng capacity cho growth và giảm tải hotspots

Inputs:
  topology, version/FCV
  capacity per shard
  shard key distribution
  zones
  write/read mix
  p95/p99 SLO
  backup health
~~~

Kết luận planning cần chỉ rõ **thêm shard có thực sự giải quyết bottleneck không**. Nếu một tenant chỉ có một shard key value nóng, phải giải quyết key design trước hoặc song song.

### 18.2. Phase B — Provision

- Tạo replica set shard mới theo chính sách HA.
- Cấu hình đúng hosts/network/TLS/internal authentication.
- Xác minh phiên bản tương thích.
- Cấp storage/IOPS headroom.
- Tích hợp monitoring/backup.
- Xác minh health độc lập.

Không dùng một mongod standalone tự phát làm shard production chỉ để tiết kiệm vài nodes.

### 18.3. Phase C — Add

Quản trị viên có thể dùng sh.addShard qua mongos theo tài liệu deployment. Ghi result, shard ID, time, configuration diff trong change record.

Sau add, **chưa coi là hoàn tất**.

### 18.4. Phase D — Monitor rebalance

Theo dõi:

~~~text
old shard distribution
      |
addShard
      |
range migrations
      |
new distribution
      |
stable workload
~~~

Trong lúc chạy:

- So app SLO.
- Xem migration failures/retries.
- Theo dõi shard disk/network.
- Xem zones/ranges còn lệch.
- Kiểm tra write concern và replication.

### 18.5. Phase E — Verify

Thành công khi:

1. Shard mới healthy.
2. Collections/ranges có placement hợp policy.
3. Data skew/hotspot giảm như mục tiêu.
4. Queries vẫn đúng và số liệu nghiệp vụ nhất quán.
5. p95/p99 và error rate trong SLO.
6. Backup/restore/monitoring cập nhật.
7. Không còn migration failure kéo dài không giải thích.

### 18.6. Phase F — Handover

Lưu:

- Thời điểm add shard.
- Shard/replica set hosts.
- Data moved và duration.
- SLO before/after.
- Warnings/incidents.
- Remaining risks.
- Capacity forecast mới.

## 19. Runbook REMOVE SHARD chi tiết

### 19.1. Phase A — Preflight

Không bắt đầu nếu chưa có:

- Capacity còn lại và headroom.
- Zone placements hợp lệ.
- Danh sách collections/ranges đang ở shard cần loại.
- Danh sách unsharded collections/database primary.
- Backup/restore status.
- Quy trình di chuyển dữ liệu được version hỗ trợ.
- SLO và stop conditions.
- Quyền và owner của change.

### 19.2. Phase B — Bắt đầu draining

Quản trị viên dùng removeShard trên mongos trong maintenance plan. Ghi response; theo dõi trạng thái draining.

### 19.3. Phase C — Phân phối dữ liệu

Balancer di chuyển ranges tới các shard còn lại theo constraints. Chỉ khi:

- Capacity/zone đủ.
- Không có range không thể di chuyển.
- Các operations cần thiết được hỗ trợ.

thì draining mới có thể hoàn tất.

### 19.4. Phase D — Những đối tượng còn lại

Kiểm tra:

- Ranges còn trên shard.
- Databases mà shard đang là primary.
- Unsharded collections.
- Các blockers do zones hoặc invalid configuration.
- Slow/failed migrations.

Không cho rằng số ranges về 0 thì mọi dependency khác cũng đã biến mất.

### 19.5. Phase E — Confirm completed

Chỉ decommission khi MongoDB/monitoring xác nhận shard removal **completed** theo API/version, không chỉ khi command trả started.

### 19.6. Phase F — Decommission

Thực hiện sau completed:

- Dừng và gỡ infrastructure cũ theo runbook.
- Cập nhật inventory/alerts/backup policies.
- Thu hồi host certificates/secrets.
- Xóa/sanitize storage đúng policy.
- Quan sát cluster sau khi data migration dừng.

### 19.7. Phase G — Post-change soak

Theo dõi trong một giai đoạn đủ dài để thấy:

- Peak traffic.
- Background jobs.
- Backup/replication.
- Disk growth.
- Read/write p99.
- Targeted/scatter-gather queries.

Không chỉ nhìn 5 phút sau remove hoàn tất.

## 20. Atlas scaling khác self-managed

### 20.1. Atlas cluster tiers

MongoDB Atlas có các thao tác thay cluster tier/compute/storage và sharding tùy loại deployment, subscription, feature và phiên bản. Nhiều công việc hạ tầng được Atlas automation thực hiện.

Nhưng người dùng vẫn phải chịu trách nhiệm:

- Capacity planning.
- SLO.
- Index/query design.
- Shard key.
- Data residency.
- Quyền và backup/restore policy.
- Change impact.

### 20.2. Auto-scaling

Một số Atlas deployments hỗ trợ autoscaling compute/storage trong những điều kiện nhất định. **Autoscaling không tự sửa shard key**, không bảo đảm xóa hot tenant hoặc giảm scatter-gather.

Việc scale storage **down** có thể bị hạn chế hoặc cần migration/rebuild tùy service; đừng giả định có thể đảo ngược tăng dung lượng bằng một click.

### 20.3. Atlas add/remove shards

Tùy cluster type và giao diện/API, cách thay shard count có thể khác thao tác self-managed qua mongos. Tuân theo Atlas docs cho deployment. **Không giả định chạy trực tiếp lệnh removeShard quản trị từ một client Atlas luôn được cho phép**.

### 20.4. Self-managed

Trong self-managed, operator quản lý:

- Provision hosts/volumes.
- Internal authentication và TLS.
- Replica sets, mongos, config servers.
- Networking/firewalls.
- Balancer/migration policies.
- Backup/restore.
- Monitoring và capacity.

Sự linh hoạt cao đi kèm trách nhiệm lớn. Không mô phỏng một sharded cluster production bằng vài mongod processes thiếu bảo mật rồi sử dụng ngoài môi trường lab.

## 21. Lab mongosh: mô phỏng phân bố và hot shard không đổi topology

### 21.1. Ý tưởng và giới hạn

Lab này **không yêu cầu sharded cluster thật**. Nó hoạt động trên standalone, replica set hoặc sharded MongoDB nơi user có quyền tạo database/collection của lab.

Ta seed 2.400 synthetic events với:

- Một tenant lớn **t001** có nhiều dữ liệu và nhiều traffic.
- Các tenants nhỏ hơn.
- **currentBucket** mô phỏng một chính sách đặt dữ liệu tệ: mọi document của t001 đi vào bucket 0.
- **proposedBucket** mô phỏng placement trải đều theo event ID.
- **approxBytes** ước lượng độ lớn để thấy “đếm documents” không nói toàn bộ story.
- **trafficWeight** mô phỏng mức hotness.

**Bucket là field minh họa trong document, không phải shard thật.** MongoDB **không di chuyển documents giữa shards** khi ta thay giá trị currentBucket/proposedBucket. Bài lab chỉ tính phân bố giả định để học capacity planning; thay đổi placement thật cần shard key/resharding và balancer trong deployment hỗ trợ.

### 21.2. Seed 2.400 documents có thể chạy lại

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_scaling_lab_381");
  const events = lab.getCollection("lab_events");
  const tag = "scale381-v1";
  const n = 2400;
  const batchSize = 200;
  let ops = [];

  function flush() {
    if (ops.length === 0) return;
    events.bulkWrite(ops, { ordered: false });
    ops = [];
  }

  for (let i = 0; i < n; i++) {
    const tenantId = i % 10 < 6
      ? "t001"
      : "t" + String(2 + i % 9).padStart(3, "0");
    const id = "b381-event-" + String(i).padStart(6, "0");
    const currentBucket = tenantId === "t001" ? 0 : i % 4;
    const proposedBucket = i % 4;

    const doc = {
      _id: id,
      labTag: tag,
      tenantId,
      region: ["HCM", "HN", "DN"][i % 3],
      createdAt: new Date(Date.UTC(2026, 0, 1) + i * 60000),
      currentBucket,
      proposedBucket,
      approxBytes: i % 20 === 0 ? 51200 : 1024 + (i % 3) * 1024,
      trafficWeight: tenantId === "t001" ? 20 : 1,
      eventType: i % 3 === 0
        ? "booking_created"
        : "listing_viewed"
    };

    ops.push({
      replaceOne: {
        filter: { _id: id, labTag: tag },
        replacement: doc,
        upsert: true
      }
    });

    if (ops.length >= batchSize) flush();
  }
  flush();

  events.createIndex(
    { labTag: 1, tenantId: 1 },
    { name: "ix_381_lab_tenant" }
  );
  events.createIndex(
    { labTag: 1, currentBucket: 1 },
    { name: "ix_381_lab_current_bucket" }
  );

  printjson({
    seeded: events.countDocuments({ labTag: tag }),
    sample: events.find(
      { labTag: tag },
      {
        _id: 1,
        tenantId: 1,
        currentBucket: 1,
        proposedBucket: 1,
        trafficWeight: 1
      }
    ).sort({ _id: 1 }).limit(5).toArray()
  });
})();
~~~

Kết quả mong đợi: **seeded = 2400**. Lệnh bulkWrite chỉ upsert các _id thuộc lab; nếu có document khác trùng _id nhưng không có labTag, operation có thể lỗi duplicate key thay vì ghi đè. Không drop collection để “sửa nhanh”.

### 21.3. Đếm tenant và hotness

~~~javascript
const lab = db.getSiblingDB("mongo_scaling_lab_381");
const events = lab.getCollection("lab_events");

printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: "$tenantId",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        trafficWeight: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { trafficWeight: -1 } }
  ]).toArray()
);
~~~

Giải thích: nếu **t001** có nhiều documents và **trafficWeight** cao, một shard chứa tất cả t001 sẽ có nguy cơ hot, ngay cả khi những shards khác có tổng disk tương đối cân bằng.

### 21.4. Phân bố hiện tại theo bucket

~~~javascript
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: "$currentBucket",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Bucket 0 sẽ có mức **syntheticLoad** lớn vì t001 luôn được gán vào đó. Các buckets khác có thể rảnh hơn. Đây là mô phỏng **placement skew** do cách chia theo tenant.

### 21.5. Phân bố giả định sau khi đổi chiến lược

~~~javascript
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: "$proposedBucket",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Vì proposedBucket là i % 4, các events và weights được trải đều hơn. Nhưng:

- proposedBucket **không phải MongoDB shard key hiện có**.
- Quy tắc i % 4 chỉ là mô hình deterministic trong lab, không phải hash function của MongoDB hashed shard key.
- Đưa thiết kế tương ứng vào production có thể cần **resharding**, compound key, index updates và thay query patterns.
- Phân tán event của một tenant cũng có thể làm truy vấn theo tenant phải target nhiều shards.

### 21.6. Đo phạm vi chênh lệch

~~~javascript
function summarizeBuckets(fieldName) {
  const groupId = "$" + fieldName;
  return events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $group: {
        _id: groupId,
        docs: { $sum: 1 },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
}

const oldBuckets = summarizeBuckets("currentBucket");
const newBuckets = summarizeBuckets("proposedBucket");

function spread(rows) {
  const weights = rows.map(x => x.syntheticLoad);
  const max = Math.max(...weights);
  const min = Math.min(...weights);
  return { max, min, maxOverMin: min ? max / min : null };
}

printjson({
  current: { rows: oldBuckets, spread: spread(oldBuckets) },
  proposed: { rows: newBuckets, spread: spread(newBuckets) }
});
~~~

**max/min** là phép so sánh thô của load giả định, không thay thế p95/p99 của requests thật. Cần đánh giá cả disk bytes, index size và query routing trước khi kết luận phương án mới tốt.

### 21.7. Tính data phải di chuyển trong mô hình

~~~javascript
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $project: {
        changedBucket: {
          $ne: ["$currentBucket", "$proposedBucket"]
        },
        approxBytes: 1
      }
    },
    {
      $group: {
        _id: "$changedBucket",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" }
      }
    }
  ]).toArray()
);
~~~

Kết quả cho biết bao nhiêu **documents/estimated bytes** sẽ đổi bucket theo mô hình. Đây là **một ước lượng giả định**, không tính chi phí index, journal/oplog, metadata, replication, concurrency hoặc những constraints của balancer.

### 21.8. Mô phỏng scale-in từ bốn buckets còn ba

Một heuristic đơn giản:

~~~javascript
// Không ghi dữ liệu; chỉ mô phỏng đích mới.
printjson(
  events.aggregate([
    { $match: { labTag: "scale381-v1" } },
    {
      $project: {
        destination: { $mod: ["$proposedBucket", 3] },
        approxBytes: 1,
        trafficWeight: 1
      }
    },
    {
      $group: {
        _id: "$destination",
        docs: { $sum: 1 },
        approxBytes: { $sum: "$approxBytes" },
        syntheticLoad: { $sum: "$trafficWeight" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray()
);
~~~

Vì bucket 3 bị ánh xạ lại vào bucket 0, mô hình này **không chắc cân bằng tốt**. Bài học: scale-in cần capacity model và placement policy cụ thể, không chỉ phép mod đơn giản.

### 21.9. Không dùng lab để đo throughput migration thật

Aggregation trên 2.400 records trong một database không phản ánh:

- Network copy giữa shard replica sets.
- Balancer coordination.
- Replication lag.
- Dung lượng index và storage.
- Chunk/range metadata.
- Real user p99.

Muốn benchmark migrations, cần một **sharded staging cluster được phép**, dữ liệu/workload tương đương và monitoring phù hợp. Lab hiện tại chỉ dạy cách phân tích **khả năng phân bố và capacity**.

## 22. Read-only diagnostics trên sharded staging cluster

Nếu có một cluster staging đã cấu hình sharding và quyền xem trạng thái, có thể kiểm tra qua mongos:

~~~javascript
// Kết nối tới mongos, không phải mongod standalone.
sh.status();

const admin = db.getSiblingDB("admin");
printjson(admin.runCommand({ listShards: 1 }));
~~~

Đối với sharded collection cụ thể, các phiên bản mongosh có thể hỗ trợ helper:

~~~javascript
// Thay bằng namespace đã sharded trong staging.
db.getSiblingDB("rental_staging")
  .getCollection("listings")
  .getShardDistribution();
~~~

Khả năng helper và output thay đổi theo phiên bản. Nếu không được hỗ trợ, dùng các MongoDB admin/Atlas monitoring APIs hiện có thay vì tự sửa hoặc suy luận từ internal config metadata.

Không chạy **sh.addShard**, **removeShard**, **reshardCollection**, **sh.stopBalancer** hay **rs.reconfig** như một phần của lab read-only này.

## 23. Khi nào cần resharding thay vì chỉ add shards?

### 23.1. Những dấu hiệu mạnh

- Một shard gần như nhận tất cả writes.
- Cùng một shard key value đại diện quá nhiều dữ liệu.
- Thêm shards nhưng hot shard không giảm.
- Range/chunk khó chia do key không phù hợp.
- Query routing scatter-gather phổ biến.
- Zones/tenant isolation yêu cầu một mô hình phân bố khác.

### 23.2. Phân biệt refine và reshard

**Refine shard key** và **reshard collection** là những cơ chế khác nhau về điều kiện và tác động:

- Refine thay đổi key pattern theo quy tắc được MongoDB hỗ trợ, thường thêm trường vào shard key hiện có.
- Reshard có thể xây dựng cách placement mới theo một shard key khác.

Không dùng hai thuật ngữ như một API duy nhất. Cần xem hỗ trợ, giới hạn, index requirements và nghiệp vụ của đúng server version.

### 23.3. Điều kiện thành công

Trước khi reshard:

1. Có shard key mới với phân bố được đo.
2. Queries có thể định tuyến phù hợp.
3. Giữ được yêu cầu unique constraints nếu có.
4. Đủ storage cho dữ liệu tạm và index.
5. Đã dự tính network/write amplification.
6. Có backup/restore và version-compatible procedure.
7. Có SLO và khả năng xử lý pause/error.
8. Có post-change validation.

### 23.4. Không đảo ngược trong một giây

Sau khi reshard hoàn tất, đổi về key cũ thường là một **thao tác dữ liệu mới** chứ không phải flip một boolean. Cần thiết kế rollback/forward fix với trạng thái thực của cluster, không hứa hoàn nguyên tức thì.

## 24. Quản lý rủi ro khi đang migration

### 24.1. Những hoạt động có thể xung đột

Trong migration/rebalance, hạn chế các thay đổi không cần thiết:

- Concurrent resharding và schema migration lớn.
- Index builds trên nhiều collections.
- Massive bulk import.
- Các maintenance jobs tiêu thụ disk/network.
- Aggressive backup/snapshot làm chậm storage.
- Thay routing/zone policy liên tục.

Không nhất thiết mọi kết hợp đều bị MongoDB cấm, nhưng nhiều thay đổi đồng thời làm khó đo, khó rollback và tăng nguy cơ vượt SLO.

### 24.2. Transaction dài

Transactions hoặc operations dài có thể khiến những giai đoạn di chuyển/commit/cleanup phức tạp hơn. Theo dõi transaction duration, retries, write conflicts và những hoạt động DDL tương ứng.

### 24.3. Throttle migration không phải giải pháp vô hạn

Giảm tốc migration có thể giúp p99 tốt hơn nhưng kéo dài thời gian còn data skew/capacity pressure. Tăng tốc có thể rút ngắn drain nhưng gây disk/network contention.

Cần chọn mục tiêu bằng trade-off:

~~~text
Migration speed
       vs
Application SLO
       vs
Disk/IOPS headroom
       vs
Operation window
~~~

### 24.4. Backup và restore

Trước topology change phải có backup theo chính sách, nhưng backup cũng cần nhất quán với topology. Với sharded cluster, phục hồi toàn cluster có yêu cầu phối hợp shards/config servers. Không coi snapshot độc lập từng host là bản backup nhất quán chỉ vì tất cả snapshots đều tồn tại.

### 24.5. Security

Thêm shard có nghĩa thêm hosts/volumes/network paths và secrets. Mỗi thành phần mới cần:

- TLS và internal authentication.
- Network ACL đúng.
- Host hardening.
- Secret/certificate rotation.
- Monitoring/audit access.
- Backup encryption.

Scale-in cần thu hồi credentials của hệ cũ để không để lại đường truy cập vô chủ.

## 25. Sự cố điển hình và cách phản ứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Add shard xong nhưng dữ liệu không sang | Balancer, zones, key/placement constraints | Kiểm tra status và policy |
| Chỉ một shard vẫn hot | Hot key, hot tenant, scatter-gather | Phân tích shard key/query mix |
| Initial sync secondary quá chậm | Network/disk/source load | Theo dõi lag/IOPS/oplog |
| Add member làm majority chập chờn | Votes/quorum/elections sai kế hoạch | Kiểm tra rs.conf và HA |
| Migration p99 cao | Copy/catch-up/IO contention | Theo dõi donor/recipient, giảm tốc có kiểm soát |
| Disk không giảm sau move | Orphan cleanup/index/filesystem behavior | Theo dõi cleanup, không xóa thủ công |
| Range không move được | Jumbo/unsplittable/zone constraints | Điều tra key và logs theo version |
| Remove shard trạng thái ongoing lâu | Chưa drain hết, unsharded/primary deps | Xem blockers và progress |
| Remove shard gặp thiếu capacity | Shards còn lại không đủ headroom | Dừng kế hoạch shrink, tăng capacity |
| Zone chỉ có shard bị loại | Không còn placement hợp lệ | Điều chỉnh zone capacity đúng policy |
| Reads stale hơn sau thêm secondary | Read preference/replication lag | Điều chỉnh consistency và routing |
| Write p99 tăng sau thêm member | Replication/quorum/IO pressure | Kiểm tra majority, initial sync |
| Backup chỉ có từ shards cũ | Shard mới chưa được backup | Cập nhật backup coverage |
| Sharded query chậm sau add | Scatter-gather hoặc network fan-out | Đo targeting/query plan |
| CPU cluster không cao nhưng API timeout | Pool wait/network/slow shard | Đo driver + per-shard metrics |
| Mất primary trong rolling maintenance | Không đủ quorum/failure domain | Dừng thay đổi, khôi phục HA |
| Thay shard key không cải thiện | Query mismatch/skew còn tồn tại | So baseline sau reshard |
| Stop balancer rồi quên bật lại | Cluster không rebalance/drain | Alert, ownership và start runbook |
| Decommission sớm | Mất range/metadata dependency | Chờ MongoDB completed |
| Scale down instance quá nhỏ | Cache/IO pressure, failover lâu | Capacity test và rollback |

## 26. Case study: tenant lớn làm shard quá tải

### 26.1. Hiện trạng

~~~text
Shard A: 70% requests, 60% dữ liệu
Shard B: 15% requests, 20% dữ liệu
Shard C: 15% requests, 20% dữ liệu

SLO:
  Search p99 <= 400 ms

Thực tế:
  Search p99 = 850 ms ở peak
~~~

### 26.2. Đề xuất A: thêm shard D

Mặt tốt: có thêm capacity. Nhưng nếu shard key là **tenantId hashed** và tenant t001 chiếm 70% requests, có thể tất cả writes t001 vẫn target một hashed value/range.

Kết quả: thêm D có thể giúp phần còn lại nhưng không chắc giảm nóng ở A.

### 26.3. Đề xuất B: nâng tài nguyên A

Có thể giảm saturation trước mắt nhưng tạo **asymmetric infrastructure** và không giải quyết khả năng tăng trưởng dài hạn nếu workload t001 tiếp tục tăng.

### 26.4. Đề xuất C: thiết kế lại shard key

Có thể chia sự kiện t001 theo một trường có cardinality cao hơn, nhưng phải xét:

- Query theo tenantId cần target bao nhiêu shards?
- Có cần index khác?
- Unique constraints có bị ảnh hưởng?
- Có zone/data residency?
- Tốn bao nhiêu dữ liệu phải di chuyển?
- Có đủ RPO/RTO và backup?

### 26.5. Quyết định đúng

Benchmark cả những phương án có khả năng:

- Giảm p99 ở offered peak.
- Tăng throughput thực.
- Không tăng lỗi/retry bất thường.
- Có cost phù hợp.
- Duy trì HA/backup.

Đừng chọn chỉ vì số shards sau change trông “đều” trên sơ đồ.

## 27. Case study: muốn giảm từ bốn shards xuống ba

### 27.1. Hiện trạng

~~~text
4 shards, mỗi shard ~600 GB data/index
Tổng ~2,4 TB
Mỗi shard có capacity 900 GB
~~~

Sau khi loại một shard, phân bố lý tưởng là:

~~~text
3 shards, mỗi shard ~800 GB
~~~

Trên giấy còn 100 GB mỗi shard. Nhưng nếu headroom policy cần 20%, migration temp data và tăng trưởng 3 tháng tiếp theo có thể làm kế hoạch không đạt.

### 27.2. Sai lầm

Team tắt shard D vì “ít request nhất”, không kiểm tra zones, unsharded collections và primary shard. Trạng thái cluster không ổn và app nhận errors.

### 27.3. Phương án đúng

1. Capacity planning theo data/index/IOPS/growth.
2. Kiểm tra zones.
3. Kiểm kê database primary/unsharded placement.
4. Backup và chuẩn bị restore.
5. Begin removeShard theo API được hỗ trợ.
6. Giám sát drain/migrations/latency.
7. Giải quyết blockers.
8. Chờ completed.
9. Decommission sau approval.
10. Post-change soak.

### 27.4. Kết luận case

Scale-in là **di chuyển dữ liệu + giảm headroom + thay topology**, không chỉ tiết kiệm chi phí một máy. Nếu chi phí rủi ro/restore cao hơn tiền tiết kiệm, có thể chưa nên shrink.

## 28. Checklist vận hành trước khi thay đổi

### 28.1. Dữ liệu

- Có inventory collections và shard keys.
- Có thống kê phân bố data/index per shard.
- Có phân bố hot tenants/keys.
- Có zone/range placement rules.
- Có assessment jumbo/unsplittable ranges.
- Có phân tích query targeting.

### 28.2. Hạ tầng

- Disk, IOPS, network, CPU/RAM headroom.
- Replica set majority/quorum khỏe.
- Oplog window đủ.
- Mongos/CSRS healthy.
- Versions/FCV tương thích.
- TLS/auth/secrets đúng.

### 28.3. Backup và SLO

- Backup gần nhất usable.
- Restore drill đã được kiểm chứng.
- RPO/RTO đã phê duyệt.
- Latency p95/p99 và error baselines.
- Có stop conditions.
- Có người trực xử lý incident.

### 28.4. Kế hoạch

- Có change owner và window.
- Các commands đúng deployment/version.
- Có thứ tự bước và xác nhận kết quả từng phase.
- Có rollback/forward-fix strategy.
- Có dashboard/alerts.
- Có communication tới application owners.

## 29. Checklist hậu kiểm

### 29.1. Topology

- Số shards/members đúng kế hoạch.
- Replica sets healthy.
- Primary/election/quorum ổn.
- Không còn hosts cũ ngoài ý muốn trong routing/monitoring.

### 29.2. Data placement

- Ranges/collections đáp ứng zone policy.
- Data skew theo mục tiêu.
- Không còn migration failures chưa xử lý.
- Remove shard đã completed nếu scale-in.
- Không có unsharded/database primary blockers.

### 29.3. Nghiệp vụ

- Search, booking, write và transaction smoke tests đạt.
- Dữ liệu tenant/region được truy cập đúng.
- Application p95/p99, errors và successful throughput đạt.
- Read/write consistency policy vẫn đúng.

### 29.4. Vận hành

- Backup/restore coverage cập nhật.
- Monitoring/alerts đủ cho shard mới.
- Secrets/certificates của shard cũ đã xử lý.
- Cost/capacity forecast cập nhật.
- Change record lưu data moved, thời gian, issues và lessons.

## 30. Bài tập thực hành

### Bài 1 — Phân biệt các cách scale

Một replica set ba members đầy disk trên mọi data-bearing nodes. Thêm secondary có giảm lượng data mỗi node phải lưu không? So sánh với scale-up storage và sharding.

### Bài 2 — Quyền ghi

Thêm hai secondaries vào một replica set có primary. Ghi của ứng dụng có tự được chia thành ba primaries không? Nêu tác động tới HA và khả năng đọc.

### Bài 3 — Inventory

Lập checklist các metrics/topology cần ghi trước khi thêm shard: FCV, roles, zones, shard key, disk, network, backup, p99 và replication.

### Bài 4 — Majority

Giải thích vì sao thay số voting members có thể ảnh hưởng majority quorum và elections. Một non-voting secondary có tham gia majority votes không?

### Bài 5 — Initial sync

Replica set có 1,2 TB data. Thêm secondary mới. Những yếu tố nào làm initial sync kéo dài và có thể gây áp lực lên sync source?

### Bài 6 — Read scaling

Ứng dụng luôn dùng primary read preference. Thêm secondary có giảm read load primary không? Nếu chuyển secondaryPreferred thì phát sinh trade-off consistency nào?

### Bài 7 — Add shard

Liệt kê các điều kiện phải đạt trước khi gọi addShard: network, TLS/internal authentication, replica set, storage, backup, monitoring, zones và SLO.

### Bài 8 — Balancer

Thêm shard D nhưng 24 giờ sau dữ liệu vẫn chủ yếu nằm ở A/B/C. Bạn sẽ điều tra những nhóm nguyên nhân nào trước khi tự chạy manual move?

### Bài 9 — Chuyển 600 GB

Ước lượng thời gian lý tưởng chuyển 600 GB với throughput hữu ích 50 MB/s theo đơn vị thập phân. Vì sao thực tế có thể lâu hơn?

### Bài 10 — Donor và recipient

Mô tả các giai đoạn chính của một range migration ở mức khái niệm. Vì sao có thể còn dữ liệu tạm trên donor sau khi ownership đổi?

### Bài 11 — Data vs heat balance

Ba shards đều 400 GB nhưng shard A nhận 80% write traffic. Có thể gọi cluster đã cân bằng chưa? Nên thêm metrics nào?

### Bài 12 — Hot tenant

Tenant t001 chiếm 70% writes; shard key là hashed tenantId. Tại sao thêm shard chưa chắc chia được traffic của t001?

### Bài 13 — Monotonic shard key

Sự kiện được shard theo createdAt tăng dần. Những writes mới có thể tạo hotspot ở đâu và bạn sẽ đánh giá key design thế nào?

### Bài 14 — Scatter-gather

Thêm shards làm số shard đích tăng, nhưng query không chứa shard key. Hiệu năng có thể xấu đi vì sao?

### Bài 15 — Jumbo/unsplittable

Balancer liên tục lỗi khi di chuyển một range lớn. Nêu cách kiểm tra shard key cardinality, zones và logs mà không sửa metadata bằng tay.

### Bài 16 — Zone policy

Zone VN chỉ có shard A, team muốn remove A. Cần thay đổi gì về zone capacity và data residency trước khi drain?

### Bài 17 — Remove shard

Vì sao không thể shutdown shard D ngay khi muốn giảm từ bốn shards còn ba? Mô tả state draining.

### Bài 18 — Unsharded data

Một shard đang làm database primary và chứa unsharded collections. Vì sao range migration của sharded collections không đủ để gỡ shard?

### Bài 19 — Capacity shrink

Cluster có 4 × 600 GB data/index, mỗi shard capacity 900 GB. Mục tiêu còn ba shards. Tính distribution lý tưởng và đánh giá headroom/risk.

### Bài 20 — Cân nhắc scale down

Sau khi scale-in, latency p99 cao hơn, disk free chỉ còn ít, và replication lag tăng. Những hành động ưu tiên nào cần làm? Có nên xóa luôn shard cũ không?

### Bài 21 — fsync/backup

Tại sao phải kiểm tra backup/restore trước topology change? Nếu backup từng shard ở thời điểm khác nhau, có thể coi đó là backup nhất quán của sharded cluster không?

### Bài 22 — SLO

Đặt guardrails p95, p99, error, disk headroom và replication lag cho một migration dài nhiều giờ. Khi nào nên pause?

### Bài 23 — Stop balancer

Một operator gọi stopBalancer và quên bật lại. Điều này có thể ảnh hưởng rebalance/draining ra sao?

### Bài 24 — Rollback

Đã chuyển 200 ranges sang shard mới, sau đó phát hiện network lỗi. Vì sao không thể gọi removeShard ngay để “rollback tức thì”?

### Bài 25 — Lab seed

Chạy lab mục 21 với 2.400 documents. Kiểm tra tenant distribution, currentBucket/proposedBucket và trafficWeight.

### Bài 26 — Current skew

Chạy aggregation theo currentBucket. Bucket nào nóng nhất? Vì sao số documents không đủ để xác định sức ép thực?

### Bài 27 — Proposed placement

Chạy aggregation theo proposedBucket. Load synthetic có phân bố đều hơn không? Những trade-off query targeting nào chưa được mô phỏng?

### Bài 28 — Data movement estimate

Đếm documents/approxBytes có currentBucket khác proposedBucket. Tại sao đó không phải số bytes physical migration thật?

### Bài 29 — Scale-in simulation

Mô phỏng bốn buckets còn ba bằng proposedBucket % 3. Bucket 0 có thể quá tải vì sao? Hãy đề xuất heuristic cân bằng khác.

### Bài 30 — Shard diagnostics

Trên sharded staging được phép, dùng sh.status/listShards và công cụ monitoring để ghi topology, phân bố và tiến trình migrations. Vì sao không tự sửa config.chunks?

### Bài 31 — Resharding

So sánh refine shard key và reshardCollection. Nêu những điều kiện về index, query routing, uniqueness, disk, version và migration risk.

### Bài 32 — Node decommission

Sau khi MongoDB xác nhận shard đã remove completed, cần xử lý những gì về disks, credentials, certificates, monitoring, cost và backup catalog?

### Bài 33 — Atlas vs self-managed

Đưa ra các câu hỏi phải xác minh trước khi thay số shards trong MongoDB Atlas. Vì sao autoscaling tài nguyên không tự sửa một shard key bị hot?

### Bài 34 — End-to-end runbook

Hệ thống bốn shards có 5 TB dữ liệu, 30% traffic từ một tenant, p99 tìm kiếm 700 ms vượt SLO 400 ms, và muốn thêm một shard. Hãy lập kế hoạch đầy đủ: root-cause, key distribution, capacity, addShard, rebalance, monitoring, error thresholds, backup, stop conditions và post-change verification.

### Bài 35 — Giảm cụm một cách an toàn

Sau tối ưu query, nhóm muốn từ năm shards về bốn. Hãy lập capacity forecast 6 tháng, zone placement checks, removeShard draining runbook, unsharded collection moves, SLO thresholds và kiểm tra decommission.

## 31. Tài liệu tham khảo MongoDB

- MongoDB Manual — [Sharding Overview](https://www.mongodb.com/docs/manual/sharding/).
- MongoDB Manual — [Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/).
- MongoDB Manual — [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/).
- MongoDB Manual — [Data Partitioning with Chunks](https://www.mongodb.com/docs/manual/core/sharding-data-partitioning/).
- MongoDB Manual — [Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/).
- MongoDB Manual — [Add Shards to a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/add-shards-to-shard-cluster/).
- MongoDB Manual — [Remove Shards from a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/remove-shards-from-cluster/).
- MongoDB Manual — [Zones](https://www.mongodb.com/docs/manual/core/zone-sharding/).
- MongoDB Manual — [Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/).
- MongoDB Manual — [Replica Set Members](https://www.mongodb.com/docs/manual/core/replica-set-members/).
- MongoDB Manual — [Add Members to a Replica Set](https://www.mongodb.com/docs/manual/tutorial/expand-replica-set/).
- MongoDB Manual — [Remove Members from Replica Set](https://www.mongodb.com/docs/manual/tutorial/remove-replica-set-member/).
- MongoDB Manual — [Initial Sync](https://www.mongodb.com/docs/manual/core/initial-sync/).
- MongoDB Manual — [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).
- MongoDB Manual — [Backup Methods](https://www.mongodb.com/docs/manual/core/backups/).
- MongoDB Atlas — [Modify a Cluster](https://www.mongodb.com/docs/atlas/scale-cluster/).
- MongoDB Atlas — [Auto-Scaling](https://www.mongodb.com/docs/atlas/cluster-autoscaling/).

**Kết luận:** **Mở rộng hoặc thu hẹp MongoDB cluster không chỉ là thêm/bớt máy.** Thêm **replica-set member** tăng dự phòng và có thể hỗ trợ đọc, nhưng không chia write load hoặc dung lượng của một replica set. Thêm **shard** mở rộng khả năng phân bố dữ liệu, nhưng hiệu quả phụ thuộc **shard key, query targeting, zones và balancer**; các **range migrations** tiêu thụ network/disk và cần đo tác động lên p95/p99, replication và lỗi ứng dụng. Khi **remove shard**, phải **drain** toàn bộ dữ liệu và xử lý unsharded collections/database primary theo version, chờ MongoDB xác nhận completed rồi mới decommission. Nếu hot key không thể chia, **resharding** có thể cần thiết hơn việc thêm shard. Mọi thay đổi topology phải có **capacity planning, backup, stop conditions, monitoring, kiểm tra quyền và hậu kiểm**; mục tiêu cuối cùng là **data placement hợp lệ, hệ thống còn đủ headroom và dịch vụ đạt SLO trong khi cũng như sau khi di chuyển dữ liệu**.
