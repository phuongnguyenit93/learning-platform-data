# Mục tiêu sẵn sàng cao và giới hạn mở rộng của một máy chủ

## 1. Bài toán: một Neo4j mạnh có đủ cho mọi mục tiêu không?

Một ứng dụng quản lý khách hàng có thể dùng Neo4j để lưu `(:Customer)-[:PLACED]->(:Order)`, tra cứu các quan hệ liên kết, phát hiện mẫu giao dịch và ghi đơn hàng qua Java Driver/Spring Data Neo4j. Khi mới triển khai, một Neo4j server với CPU, RAM, SSD và page cache phù hợp có thể đáp ứng toàn bộ nhu cầu. Nhưng khi lưu lượng tăng hoặc cần phục vụ liên tục, hai câu hỏi khác nhau xuất hiện:

1. **Sẵn sàng cao (high availability, HA):** hệ thống còn trả lời được truy vấn hoặc chấp nhận ghi khi một server, ổ đĩa, đường mạng hay vùng triển khai gặp lỗi không?
2. **Mở rộng (scaling):** khi dữ liệu, số client hoặc tải đọc/ghi tăng, có thể tăng năng lực đến đâu bằng cách nâng cấu hình một máy; khi nào phải phân phối công việc?

Một máy được trang bị NVMe và nhiều RAM **không tự trở thành HA**: process, hệ điều hành, host, nguồn điện hoặc vùng triển khai vẫn là các điểm lỗi chung. Ngược lại, một cluster nhiều server **không tự làm mọi câu ghi Cypher nhanh hơn**. Đối với một database Neo4j thông thường, primaries phối hợp để cung cấp khả năng chịu lỗi, còn secondaries chủ yếu tăng năng lực đọc.

Trong chương **Cụm và mở rộng** của mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, bài này giải thích **mục tiêu sẵn sàng cao và giới hạn mở rộng của một máy chủ**, đặt trong bối cảnh property graph, Cypher, index/constraint, nhập dữ liệu, Java Driver và Spring Data Neo4j.

**Kết quả học tập:**

- Phân biệt availability, durability, consistency, RPO, RTO và chỉ tiêu SLI/SLO.
- Xác định điểm nghẽn CPU, RAM/page cache, I/O, transaction log, khóa và mạng của một server.
- Hiểu mô hình **primary, secondary, writer và quorum** theo từng database Neo4j.
- Giải thích vì sao **3 primaries chịu được 1 lỗi primary đối với ghi**, nhưng **1 primary + nhiều secondaries** không mang lại khả năng chịu lỗi ghi tương đương.
- Chọn scale-up, read scale-out, chia workload/database hoặc một giải pháp phân vùng dữ liệu thích hợp dựa trên phép đo.
- Thiết kế phép thử tải và kiểm thử failover trên **môi trường cô lập**, không gây gián đoạn sản xuất.

> **Phiên bản và edition:** Nội dung cluster tham chiếu Neo4j Enterprise và Operations Manual của các phiên bản hiện hành tại thời điểm viết. Cluster tự quản lý, quorum và các lệnh quản trị cụ thể **không áp dụng nguyên xi cho Community Edition hoặc mọi gói Neo4j Aura**. Mỗi release có thể thay đổi thuật ngữ, giới hạn topology, lựa chọn scale hoặc giao diện. Khi triển khai, đối chiếu tài liệu của đúng phiên bản/edition.

## 2. Sẵn sàng cao không chỉ có một con số “uptime”

Với database, một hệ thống có thể **đọc được nhưng không ghi được**, hoặc ghi được nhưng có độ trễ khiến ứng dụng hết timeout. Do đó, trước khi chọn cluster cần định nghĩa rõ “available” theo nghiệp vụ.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Read availability** | API đọc graph còn thành công trong giới hạn latency không? | Tìm đơn hàng gần đây trong 300 ms |
| **Write availability** | API tạo/cập nhật node và relationship có commit được không? | Tạo `Order` rồi nối với `Customer` |
| **Durability** | Dữ liệu đã commit có được giữ qua những lỗi nằm trong phạm vi cam kết không? | Không mất giao dịch đã được xác nhận |
| **Consistency** | Lần đọc sau có thấy giao dịch đã ghi trước hay có thể gặp dữ liệu chưa đồng bộ? | Đọc đơn hàng ngay sau khi tạo |
| **RPO** | Có thể chấp nhận mất dữ liệu đến mốc thời gian nào trong thảm họa? | RPO mục tiêu 5 phút |
| **RTO** | Mục tiêu bao lâu khôi phục dịch vụ về trạng thái phục vụ được? | RTO mục tiêu 15 phút |

**Không đánh đồng các khái niệm:**

- Thêm một replica đọc có thể cải thiện khả năng **đọc** khi writer hỏng, nhưng **không bảo đảm ghi** nếu database chỉ có một primary.
- Replication giúp chịu lỗi nhất định nhưng **không thay thế backup**, vì lệnh xóa nhầm đã commit có thể được nhân bản.
- Một hệ thống tự chuyển writer sau failover vẫn có **khoảng gián đoạn**, timeout hoặc retry; HA không đồng nghĩa 100% uptime.
- RPO/RTO thuộc kế hoạch khôi phục khi xảy ra sự cố; availability SLO đo trải nghiệm dịch vụ trong một cửa sổ thời gian.

### 2.1. Viết SLI theo hành vi người dùng

Một **Service Level Indicator (SLI)** có thể được định nghĩa:

\[
\text{Write availability SLI} =
\frac{\text{số yêu cầu ghi hợp lệ thành công đúng hạn}}
{\text{số yêu cầu ghi hợp lệ được đo}}
\]

Khi đo, cần quy định rõ mẫu số: có tính request bị mạng chặn trước khi tới database không, timeout có được coi là lỗi không, response sau retry có được coi là thành công không, và request không hợp lệ có bị loại không.

Có thể tạo SLI tương tự cho read với điều kiện `latency <= ngưỡng`. Đo một câu `RETURN 1` không đủ đại diện cho API tìm đường đi qua graph hoặc giao dịch tạo nhiều relationship.

## 3. Tính error budget từ mục tiêu availability

Giả sử cửa sổ SLO dài **30 ngày**:

\[
T = 30\times24\times60 = 43.200\text{ phút}
\]

\[
\text{Downtime budget} = T \times (1 - \text{SLO})
\]

| SLO availability giả định | Khoảng gián đoạn tối đa theo thời gian trong 30 ngày |
|---|---:|
| 99% | 432 phút = 7 giờ 12 phút |
| 99,9% | 43,2 phút = 43 phút 12 giây |
| 99,95% | 21,6 phút = 21 phút 36 giây |
| 99,99% | 4,32 phút = 4 phút 19,2 giây |

Đây là **quy đổi lý thuyết** khi dùng SLO tính trên thời gian; với SLO tính theo tỷ lệ request thành công, không tự động đổi chính xác ra số phút nếu lưu lượng thay đổi theo giờ.

Ví dụ ứng dụng đặt hàng đặt **write availability 99,95%** trong 30 ngày. Một đợt failover kéo dài 3 phút sẽ tiêu thụ một phần của budget 21,6 phút. Nếu bảo trì, lỗi mạng, timeout ứng dụng và các lần failover cộng lại vượt budget, mục tiêu không đạt dù mỗi server đều “có lúc đang chạy”.

**Điểm thực dụng:** đặt **read SLO** và **write SLO** riêng nếu khả năng phục vụ của chúng khác nhau. Chỉ số `SHOW SERVERS` báo server còn liên lạc được không chứng minh truy vấn nghiệp vụ đã đạt SLO.

## 4. Một máy chủ có những điểm lỗi chung nào?

~~~mermaid
flowchart TB
    U["Ứng dụng Java / Spring Data Neo4j"] --> N["Một Neo4j server"]
    N --> P["Neo4j process + JVM"]
    N --> C["CPU, heap, page cache và native memory"]
    N --> S["Volume: store, indexes, transaction log"]
    N --> W["NIC, DNS, TLS và kết nối mạng"]
    N --> O["OS / VM / container / host vật lý"]
    O --> Z["Nguồn điện, AZ / data center, vận hành"]
~~~

Một server đơn lẻ có thể ngừng đáp ứng vì:

- Process crash, nâng cấp cần restart, JVM bị OOM, GC pause hoặc thiếu thread phục vụ.
- CPU bị giới hạn bởi quota container/VM, workload Cypher xấu hoặc truy vấn tạo số lượng path quá lớn.
- RAM không đủ cho heap, native memory, page cache và hệ điều hành.
- Volume đầy, lỗi filesystem, transaction log flush chậm hoặc mất toàn bộ thiết bị lưu trữ.
- NIC, DNS, TLS, firewall hoặc định tuyến làm client không kết nối được.
- Host vật lý bị thay thế, sự cố nguồn điện hoặc cả vùng triển khai gặp lỗi.
- Thao tác quản trị sai: xóa database, đổi quyền user/role, thay config hoặc deploy một plugin lỗi.

**Scale-up chỉ xử lý một số giới hạn năng lực**, không loại bỏ điểm lỗi chung. Một máy 128 CPU và 1 TiB RAM vẫn có thể dừng khi host mất điện. Có backup giúp khôi phục sau sự cố nhưng không giữ request liên tục thành công trong thời gian phục hồi.

## 5. Giới hạn mở rộng của một server: các tài nguyên cạnh tranh

| Tài nguyên | Workload gây áp lực | Dấu hiệu điển hình | Hướng xác minh |
|---|---|---|---|
| **CPU** | Traversal sâu, lọc/aggregation, parse Cypher, serialize response | CPU gần trần, p95 tăng khi thêm request | Query plan, CPU per core, sampling/profiling |
| **Heap / GC** | `collect` lớn, xử lý result, transaction state | GC pause, heap pressure, OOM | Heap/GC, transaction memory, kích thước batch |
| **Neo4j page cache** | Random lookup, traversal nhiều graph/index pages | Cache misses tăng, đọc “nguội” chậm | Page cache hit/miss và working set |
| **Đĩa / IOPS** | Random read, cập nhật index, checkpoint | I/O latency và queue depth tăng | OS/cloud volume metrics và `PROFILE` |
| **Transaction log** | Nhiều transaction ghi, commit nhỏ liên tục | Commit p95/p99 tăng; log volume áp lực | Write latency, log activity, batching |
| **Khóa** | Nhiều writer cập nhật cùng ID/supernode | Lock waits, retry/deadlock, throughput đứng yên | Transaction wait/lock diagnostics |
| **Mạng** | Trả graph rất lớn, nhiều round trip nhỏ | RTT/bytes/s cao, timeout | Client tracing, NIC metrics, payload |
| **Connection pool** | Session/result không được đóng, quá nhiều client | Acquire timeout dù server chưa bão hòa | Pool metrics, thời gian giữ Session |

Không có một con số “số node tối đa trên một server” dùng cho mọi graph. Khả năng thực tế phụ thuộc kích thước property, mật độ relationship, phân bố bậc node, số index, workload, RAM, storage latency, cache và các yêu cầu SLO.

### 5.1. Nút siêu kết nối (*supernode*)

Giả sử một node `(:Topic {name:'popular'})` có hàng triệu relationship. Truy vấn:

~~~cypher
MATCH (t:Topic {name:$name})-[:MENTIONED_BY]->(p:Post)
RETURN p
~~~

có thể tạo tập kết quả quá lớn, gây chi phí expand, result serialization và mạng cao. Thêm RAM hoặc nhiều secondary **không tự khắc phục** một request có thuật toán/truy vấn cần xử lý hàng triệu quan hệ.

Các hướng xử lý gồm: xác định mục tiêu nghiệp vụ, lọc sớm, dùng index ở điểm bắt đầu, giới hạn kết quả, tách truy vấn phân tích khỏi OLTP, hoặc mô hình hóa lại khi thật sự cần.

### 5.2. Nút thắt không nhất thiết là RAM

Page cache hit ratio 99,8% vẫn có thể đi kèm transaction commit chậm do ổ log có `fsync` latency cao. Ngược lại, một query có nhiều `DB Hits` và traversal nặng CPU có thể chậm ngay cả khi trang dữ liệu đã ở RAM. **Đo trước khi tăng bộ nhớ.**

## 6. Quy luật bão hòa: thêm concurrency không luôn tăng throughput

Trong một pipeline nhập dữ liệu hoặc một API nhiều truy vấn:

- Ký hiệu `λ` là lượng yêu cầu đến mỗi giây.
- Ký hiệu `μ` là năng lực xử lý thành công bền vững mỗi giây ở điều kiện đã đo.

Nếu `λ > μ` trong thời gian dài, backlog/hàng chờ sẽ tăng. Khi đẩy thêm client, hệ thống có thể mất thời gian đợi lock, pool hoặc I/O nhiều hơn thay vì xử lý nhanh hơn.

**Ví dụ giả định, không phải benchmark Neo4j:**

| Worker đồng thời | Throughput ghi thành công | Latency batch p95 | Tỷ lệ retry |
|---:|---:|---:|---:|
| 1 | 1.100 rows/s | 35 ms | 0% |
| 2 | 2.000 rows/s | 47 ms | 0,1% |
| 4 | 2.300 rows/s | 105 ms | 0,7% |
| 8 | 2.250 rows/s | 240 ms | 4% |

Trong ví dụ, tăng workers từ 4 lên 8 **không tăng throughput**, nhưng p95 và retry tệ hơn. Điều đó gợi ý đã tiến sát nút thắt; phải đo CPU, lock waits và storage để biết nguyên nhân chứ không thể kết luận “CPU yếu” chỉ từ bảng.

### 6.1. Amdahl: giới hạn của song song hóa

Khi một phần việc không thể song song hóa, tốc độ tăng bị giới hạn:

\[
S(N)=\frac{1}{s+\frac{1-s}{N}}
\]

với `s` là tỷ lệ tuần tự và `N` là số worker lý tưởng. Nếu `s=0,3` và `N=4`, `S(4)≈2,11` chứ không phải 4. Đây là mô hình khái niệm về hiệu năng, **không phải công thức dự báo số primary Neo4j giúp tăng tốc ghi**. Với một database cluster, write leader và quorum còn tạo chi phí replication riêng.

## 7. Tối ưu một server trước khi quyết định scale-out

Khi SLO còn đạt và rủi ro downtime đã được chấp nhận, **scale-up** có thể đơn giản và tiết kiệm chi phí vận hành hơn triển khai cluster.

Một quy trình ưu tiên:

1. **Xác nhận vấn đề nghiệp vụ:** throughput, p95/p99, tỷ lệ timeout, số request thành công, thời gian phục hồi.
2. **Kiểm tra Cypher bằng `EXPLAIN`/`PROFILE`:** index seek/scan, `Rows`, `DB Hits`, aggregation, Cartesian product, mở rộng đường đi.
3. **Bảo đảm schema đúng:** unique constraint cho ID nghiệp vụ, index phù hợp predicate/query, không thêm quá nhiều index vô ích làm chậm ghi.
4. **Giảm over-fetch:** chỉ trả cột cần, phân trang node gốc trước khi nạp relationship, tránh N+1 do Java service/SDN repository.
5. **Giảm overhead client:** dùng Driver lâu dài, Session ngắn hạn, `executeRead`/`executeWrite`, batch `UNWIND` thay vì một round trip cho mỗi node.
6. **Đo bộ nhớ:** cân bằng heap, page cache, native memory và RAM cho OS; tránh chỉ tăng cache theo cảm tính.
7. **Đo storage:** IOPS, random read latency, durable write latency, quota cloud, checkpoint, log volume.
8. **Thử tăng CPU/RAM/SSD theo từng biến**, giữ workload và dữ liệu tương đương.

Scale-up có điểm dừng: giá/CPU, RAM tối đa, trần một instance cloud, throughput storage, tốc độ một transaction và đặc điểm độc lập của ghi. Quan trọng hơn, scale-up **không giải quyết mục tiêu chịu lỗi host**. Nếu yêu cầu HA đã là bắt buộc, không nên trì hoãn thiết kế nhiều bản sao chỉ bằng việc tiếp tục nâng cấu hình một server.

## 8. Cluster Enterprise: server không đồng nghĩa role database

Theo kiến trúc Neo4j hiện hành, một **cluster** là tập server có thể chứa nhiều database. **Mỗi database có topology riêng** với các bản sao (*allocations*) ở chế độ:

- **Primary:** tham gia cơ chế ghi chịu lỗi; một primary có thể được chọn làm **writer/leader** cho database đó.
- **Secondary:** bản sao nhận cập nhật bất đồng bộ, chủ yếu phục vụ **đọc** và mở rộng năng lực đọc.

Một server có thể chứa primary của database A và secondary của database B tùy constraints/topology. Không nên nói “server này là primary cho toàn cluster” khi đang mô tả một database cụ thể.

~~~mermaid
flowchart TB
    J["Java Driver neo4j:// + routing"] --> R["Routing table theo database"]
    R --> P1["Server 1: primary DB sales (writer)"]
    R --> P2["Server 2: primary DB sales (follower)"]
    R --> P3["Server 3: primary DB sales (follower)"]
    R --> S1["Server 4: secondary DB sales"]
    P1 <-->|"Raft / quorum replication"| P2
    P1 <-->|"Raft / quorum replication"| P3
    P1 -. "Asynchronous transaction pull" .-> S1
    P2 -. "Có thể cung cấp nguồn cập nhật" .-> S1
~~~

Sơ đồ mô tả **một database `sales`**; trong một cluster nhiều database, leader của từng database có thể đặt ở server khác. Các dấu mũi tên không thay thế mô tả protocol chi tiết; điểm cần hiểu là primaries phối hợp để ghi bền, còn secondaries theo kịp qua cơ chế bất đồng bộ.

**Lưu ý:** Cluster là tính năng của các edition/deployment hỗ trợ, không phải cứ tạo ba container Neo4j Community và đặt trước một load balancer là có quorum/HA database.

## 9. Quorum: mục tiêu chịu lỗi ghi được tính thế nào?

Với nhóm primary sử dụng đa số (*majority*) để commit ghi, một cấu hình điển hình cần:

\[
Q(M)=\left\lfloor \frac{M}{2}\right\rfloor + 1
\]

trong đó `M` là số primary allocations đang được thiết kế cho một database, `Q` là số primary cần có để đạt đa số.

| Số primary | Đa số cần cho ghi | Lỗi primary có thể chịu mà vẫn còn đa số | Diễn giải |
|---:|---:|---:|---|
| 1 | 1 | 0 | Mất primary là mất khả năng ghi |
| 2 | 2 | 0 | Mất một primary thì không đủ quorum ghi |
| 3 | 2 | 1 | Cấu hình HA thông dụng, chịu lỗi một primary |
| 5 | 3 | 2 | Chịu lỗi hai primary, chi phí/độ trễ cao hơn |

Đối với mục tiêu chịu `F` lỗi primary bất kỳ trong mô hình tối thiểu thường chọn:

\[
M = 2F + 1
\]

**Ví dụ:** `F=1` cần **3 primaries** phân tán trên ít nhất ba server/failure domains phù hợp; `F=2` cần **5 primaries**. Những công thức này là điều kiện topology/quorum, **không phải cam kết SLO tuyệt đối**: mạng chia cắt, DNS/TLS, tài nguyên quá tải, failover time hoặc lỗi ứng dụng vẫn có thể khiến request thất bại.

### 9.1. Thí dụ tình huống mất một thành viên

- **Ba primary:** mất một server, còn hai primary có thể duy trì quorum, bầu writer mới nếu cần. Dịch vụ ghi có thể gián đoạn ngắn trong lúc failover và client retry.
- **Hai primary:** mất một, còn một không đạt đa số; không nên tuyên bố HA ghi khi chỉ có hai bản sao.
- **Một primary + hai secondary:** có nhiều bản sao dữ liệu phục vụ đọc, nhưng chỉ một primary có quyền writer. Nếu primary lỗi, **không có quorum primary thay thế** theo cùng topology.

Mục đích của quorum là tránh hai phía của một network partition cùng chấp nhận các chuỗi ghi mâu thuẫn. Mất quorum có thể khiến database chỉ đọc hoặc không thể ghi; **không được “sửa” bằng cách ép hai phía ghi đồng thời**.

## 10. Secondaries giúp mở rộng đọc, không biến một database thành nhiều writer

Secondaries nhận transaction từ primaries **bất đồng bộ**, nên có thể chậm hơn writer trong một khoảng thời gian. Thêm secondary cho phép phân phối nhiều read query, chẳng hạn:

- Dashboard và báo cáo đọc rộng.
- API tra cứu có số request đọc rất lớn.
- Tách phần tải phân tích khỏi primaries phục vụ giao dịch.

Nhưng thêm secondary cũng có chi phí:

- Thêm disk và RAM để chứa một bản sao database/index.
- Thêm mạng để chuyển transaction và quản lý trạng thái.
- Cần theo dõi **replication lag**, catch-up và tính nhất quán khi đọc dữ liệu vừa ghi.
- Một truy vấn read đơn lẻ vẫn có thể chậm nếu Cypher/index không phù hợp.
- Secondaries không tự tạo **nhiều writer độc lập** cho **cùng một database**.

Một cấu hình **3 primaries + 2 secondaries** thường phục vụ hai mục tiêu khác nhau: primaries bảo vệ khả năng ghi khi một thành viên lỗi, secondaries tăng read capacity. Không xem nó như “5 writer cho cùng database”.

### 10.1. Thêm primary có làm throughput ghi nhân lên?

**Không mặc định.** Với một database thông thường, **chỉ một primary là writer** tại một thời điểm. Transaction cần được replicate/acknowledge theo quorum; thêm primary có thể làm tăng độ bền/chịu lỗi nhưng cũng tăng phối hợp, mạng và latency. Nếu workload là **write-heavy**, cần tối ưu transaction, index, contention, sizing của writer; để tăng write throughput qua nhiều vùng dữ liệu, cần xem giải pháp **phân chia database/shard** theo workload được hỗ trợ, không chỉ tăng primary.

## 11. So sánh scale-up, read scale-out và phân chia dữ liệu

| Phương án | Tăng gì? | Có giải quyết HA ghi? | Hạn chế/cái giá |
|---|---|---|---|
| **Scale-up một server** | CPU, RAM, page cache, SSD/IOPS | **Không** loại điểm lỗi máy đơn | Trần phần cứng, downtime bảo trì, chi phí phần cứng |
| **3+ primaries cho database** | Fault tolerance và khả năng tiếp tục ghi khi đủ quorum | **Có** trong phạm vi lỗi được thiết kế | Network/quorum, vận hành cluster, failover/retry |
| **Thêm secondaries** | Read concurrency, giảm tải đọc primaries | **Không tự tạo thêm writer** | Replication lag, chi phí mỗi bản sao |
| **Tách nhiều database theo miền/tenant** | Cô lập tài nguyên và phân phối leader giữa database | Phụ thuộc topology từng database | Query liên database, quản lý schema/transaction, vận hành |
| **Composite database / federation hoặc sharding được hỗ trợ** | Có thể phân tán dữ liệu và một số workload đọc/ghi | Phụ thuộc kiến trúc cụ thể | Phân vùng khóa, join/traversal qua shard, tính nhất quán |
| **Managed Neo4j Aura hoặc sản phẩm mở rộng chuyên biệt** | Tùy gói và tính năng được cung cấp | Phụ thuộc SLA và chính sách dịch vụ | Giới hạn gói, mô hình trách nhiệm chia sẻ, chi phí |

Tài liệu Neo4j mới có các lựa chọn **composite database/sharding** và những sản phẩm mở rộng dành cho trường hợp dữ liệu vượt giới hạn một server. Tính năng, khả dụng trên Aura, kiểu giao dịch và khả năng triển khai thay đổi theo phiên bản. Đây là **bài toán kiến trúc riêng**, không được giả định một cluster primaries/secondaries tự chia nhỏ graph thành các shard.

Một graph có rất nhiều traversal **qua các miền/shard** có thể chịu chi phí network và hợp nhất kết quả cao hơn khi dữ liệu cùng nằm trên một máy. Quyết định phân vùng cần căn cứ mô hình truy cập thật, không chỉ số node.

## 12. Java Driver: cấu hình routing đúng để tận dụng cluster

Đối với Neo4j Java Driver, URI:

- `neo4j://` hoặc `neo4j+s://` cho phép Driver sử dụng cơ chế routing theo topology phù hợp.
- `bolt://` hoặc `bolt+s://` kết nối tới endpoint cụ thể, **không tự động thực hiện cluster routing như `neo4j://`**.

Ứng dụng nên tạo **Driver dùng chung**, chọn database tường minh và tạo Session ngắn hạn:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.neo4j.driver.Values;

public final class ClusterClientExample {
    static void run(String uri, String user, String password,
                    String database) {
        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            driver.verifyConnectivity();

            try (Session session = driver.session(
                    SessionConfig.forDatabase(database))) {
                session.executeWrite(tx -> {
                    tx.run("""
                        MATCH (o:QA001Order {orderId:$id})
                        SET o.status = 'CONFIRMED'
                        """, Values.parameters("id", "O42"))
                      .consume();
                    return null;
                });

                String status = session.executeRead(tx ->
                    tx.run("""
                        MATCH (o:QA001Order {orderId:$id})
                        RETURN o.status AS status
                        """, Values.parameters("id", "O42"))
                      .single().get("status").asString()
                );

                System.out.println(status);
            }
        }
    }
}
~~~

Với fixture ở mục 16, giá trị dự kiến khi chạy thành công trên database test là `CONFIRMED`. Cùng một Session, Driver quản lý các bookmark cần thiết để thực hiện các transaction có quan hệ nhân quả theo thứ tự.

**Điểm cần kiểm tra trên production:**

1. URI dùng TLS/certificate phù hợp và endpoint có routing hoạt động.
2. `SessionConfig.forDatabase(...)` chọn đúng database, không vô tình dùng home database của user.
3. `executeRead`/`executeWrite` biểu thị đúng mục đích và được phép retry lỗi transient thích hợp.
4. Transaction function **không chứa tác dụng phụ HTTP/email không idempotent**, vì Driver có thể gọi lại function khi failover.
5. Connection pool và timeout phù hợp với thời gian bầu writer, RTT và p95 thật; không để client tạo Driver mới mỗi request.

Đoạn code không tự tạo cluster; nó chỉ minh họa cách ứng dụng truy cập một database trên cluster **đã được triển khai và vận hành đúng**.

## 13. Bookmarks và consistency khi failover hoặc đọc từ secondary

Giả sử request A tạo một `Order`, ngay sau đó request B từ một instance Java khác đọc danh sách đơn hàng. Nếu request B được route tới một secondary đang trễ transaction, kết quả có thể chưa chứa đơn hàng vừa commit trừ khi có cơ chế quan hệ nhân quả phù hợp.

~~~mermaid
sequenceDiagram
    participant W as API ghi
    participant P as Primary writer
    participant S as Secondary
    participant R as API đọc
    W->>P: Tạo Order trong transaction
    P-->>W: Commit thành công + bookmark
    P-->>S: Nhân bản transaction bất đồng bộ
    R->>S: Đọc không có bookmark phụ thuộc
    Note over R,S: Có thể chưa thấy Order mới
    R->>S: Đọc có bookmark phù hợp
    Note over S: Đợi đạt mốc đã commit trước khi trả kết quả
~~~

**Bookmark** cho phép client mô tả mốc transaction mà truy vấn sau cần nhìn thấy. Java Driver quản lý bookmarks trong cùng Session; giữa nhiều Session hoặc nhiều instance, ứng dụng cần truyền bookmark hoặc dùng `BookmarkManager` theo đúng phạm vi.

Ví dụ Java Driver 5.x dùng bookmark manager chung cho **một workflow**:

~~~java
import org.neo4j.driver.BookmarkManager;
import org.neo4j.driver.BookmarkManagers;
import org.neo4j.driver.SessionConfig;

BookmarkManager manager = BookmarkManagers.defaultBookmarkManager();

SessionConfig workflowConfig = SessionConfig.builder()
    .withDatabase("neo4j")
    .withBookmarkManager(manager)
    .build();

// Các session thuộc cùng workflow có thể dùng workflowConfig.
~~~

**Không** tự chia sẻ bookmark manager chung cho mọi tenant, mọi user và mọi job nếu chúng không có phụ thuộc dữ liệu với nhau. Bookmark giúp đảm bảo read-your-writes khi truyền đúng mốc, nhưng có thể tăng latency do phải chờ secondary bắt kịp. Nó **không thay thế** quyền truy cập, transaction, backup hoặc chính sách consistency của nghiệp vụ.

## 14. Các tình huống lỗi: hệ thống còn phục vụ được gì?

| Tình huống | Một server | 3 primaries | 3 primaries + secondaries |
|---|---|---|---|
| Một Neo4j process/database copy bị lỗi | Mất đọc và ghi cho database đó | Có thể tiếp tục đọc/ghi nếu còn quorum và client route đúng | Có thể tiếp tục đọc/ghi; read capacity giảm tùy nơi lỗi |
| Writer/leader dừng | Không có writer khác | Các primaries còn lại có thể bầu writer mới | Tương tự, secondaries không bầu thành writer |
| Một secondary dừng | Không áp dụng | Không áp dụng | Không ảnh hưởng quorum ghi; giảm khả năng đọc |
| Một primary bị mất, còn hai primary khỏe | Không áp dụng | Còn quorum 2/3 | Còn quorum 2/3 |
| Hai primaries bị mất trong cấu hình 3 | Không áp dụng | Mất quorum ghi | Secondaries không khôi phục quorum ghi |
| Cả vùng triển khai chứa mọi primary cùng mất | Mất dịch vụ | Mất quorum / dịch vụ | Mất quorum ghi dù secondary ở vùng khác còn đọc được |
| Xóa dữ liệu hợp lệ nhưng do thao tác nhầm | Dữ liệu bị xóa | Lệnh xóa có thể replicate | Lệnh xóa có thể replicate |

Tất cả mô tả trên giả định các thành viên còn lại **khỏe**, mạng tương thích với quorum, có đủ tài nguyên, cấu hình topology chính xác và client có thể route. Thực tế có thể xảy ra timeout/retry hoặc tạm ngắt trong quá trình phát hiện lỗi/bầu writer.

### 14.1. Lỗi tương quan quan trọng hơn số container

Ba primary cùng nằm trên **một host vật lý** vẫn chia sẻ nguồn điện, RAM, storage và mạng; một lỗi host có thể làm mất cả ba. Để chịu lỗi vùng, cần phân bố primaries giữa failure domains (host/rack/AZ/data center) theo giả định và khả năng mạng.

Tuy nhiên, phân tán qua các vùng quá xa làm tăng RTT của **quorum replication**, có thể tăng latency ghi. Cần cân bằng **fault domain isolation** và **network latency ổn định**. Không lấy sơ đồ “3 AZ” làm bằng chứng rằng mọi transaction sẽ có cùng latency như một host.

## 15. Các chỉ số phải quan sát khi đánh giá HA và scaling

| Lớp | SLI/metric | Điều gì cần suy ra? |
|---|---|---|
| **Ứng dụng** | Read/write success rate, p50/p95/p99, timeout, retries | Người dùng có thật sự hoàn thành nghiệp vụ đúng hạn? |
| **Driver/pool** | Connection acquisition latency, routing errors, transaction retries | Cluster route và connection lifecycle có bền không? |
| **Cluster** | Writer/leader theo database, quorum, thành viên unavailable, election frequency | Có duy trì write leadership và chịu lỗi? |
| **Replication** | Last committed/applied tx ID, lag, catch-up time | Replica/secondary có theo kịp? |
| **Database** | Active/blocked transactions, lock waits, query execution time | Tải có bị khóa hoặc contention? |
| **CPU/RAM** | CPU per core, heap/GC, page cache hit/miss, native memory | Có nút thắt tài nguyên đơn máy? |
| **Storage** | IOPS, MiB/s, durable write p99, queue depth, disk free | Disk/log/checkpoint có làm commit chậm? |
| **Vận hành** | Failover detection time, time to healthy route, restore duration | RTO thực tế và khôi phục sau lỗi có đạt mục tiêu? |

Metrics cluster là thông tin **theo database**, không nên chỉ hỏi “cả cluster có leader không?”. Với hệ nhiều database, database `sales` có thể đang thiếu quorum trong khi `analytics` vẫn bình thường.

### 15.1. Query quan sát chỉ đọc

Với quyền phù hợp:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

Trên cluster Enterprise, account có quyền quản trị có thể xem các server:

~~~cypher
SHOW SERVERS YIELD *;
~~~

`SHOW SERVERS` giúp quan sát health/state/constraints nhưng không tự thay thế phép đo SLI nghiệp vụ hoặc xác minh dữ liệu đã replicate. Không dùng lệnh quản trị `DROP/DEALLOCATE/STOP` trên production như một “lệnh kiểm tra HA”.

Để xem hiệu năng của một truy vấn cụ thể:

~~~cypher
EXPLAIN
MATCH (o:QA001Order {orderId:'O42'})
      -[:QA001_BELONGS_TO]->(a:QA001Account)
RETURN o.orderId AS orderId, a.accountId AS accountId;
~~~

`EXPLAIN` chỉ tạo plan dự kiến và không chạy query; `PROFILE` chạy thật và có overhead. `DB Hits` là công việc logic của query, không phải số disk reads hay bằng chứng node cluster đã sẵn sàng.

## 16. Fixture có đáp án cho bài đo tải và read-after-write

Phần này dùng **database thực hành riêng**, trên một standalone instance hoặc cluster staging đã được triển khai. Không cần tạo cluster để chạy fixture. Cố định dữ liệu giúp kiểm tra tính đúng trước khi benchmark.

### 16.1. Reset đúng nhãn của bài

Chỉ trên database test không chia sẻ các label:

~~~cypher
DROP CONSTRAINT qa001_account_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa001_order_id IF EXISTS;
~~~

~~~cypher
MATCH (n)
WHERE n:QA001Account OR n:QA001Order
DETACH DELETE n;
~~~

### 16.2. Tạo constraint và 10 account

~~~cypher
CREATE CONSTRAINT qa001_account_id IF NOT EXISTS
FOR (a:QA001Account)
REQUIRE a.accountId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa001_order_id IF NOT EXISTS
FOR (o:QA001Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
UNWIND range(1,10) AS i
MERGE (a:QA001Account {accountId:'A' + toString(i)})
SET a.segment =
  CASE WHEN i <= 5 THEN 'GOLD' ELSE 'SILVER' END;
~~~

### 16.3. Tạo 100 đơn hàng và 100 relationship

~~~cypher
UNWIND range(1,100) AS i
MATCH (a:QA001Account {
  accountId:'A' + toString(((i - 1) % 10) + 1)
})
MERGE (o:QA001Order {orderId:'O' + toString(i)})
SET o.amount = i,
    o.status = 'NEW'
MERGE (o)-[:QA001_BELONGS_TO]->(a);
~~~

Tất cả ID được tạo có chủ đích. Mỗi account có đúng **10 order**. `A1` có O1, O11, ..., O91; `A10` có O10, O20, ..., O100.

### 16.4. Kết quả kiểm chứng

~~~cypher
MATCH (o:QA001Order)
RETURN count(o) AS orders,
       sum(o.amount) AS amountTotal;
~~~

| orders | amountTotal |
|---:|---:|
| **100** | **5050** |

Giải thích: tổng `1 + 2 + ... + 100 = 100 × 101 / 2 = 5050`.

~~~cypher
MATCH (a:QA001Account)
RETURN count(a) AS accounts,
       count(CASE WHEN a.segment='GOLD' THEN 1 END) AS gold,
       count(CASE WHEN a.segment='SILVER' THEN 1 END) AS silver;
~~~

| accounts | gold | silver |
|---:|---:|---:|
| **10** | **5** | **5** |

~~~cypher
MATCH ()-[r:QA001_BELONGS_TO]->()
RETURN count(r) AS relationships;
~~~

**Đáp án:** `relationships = 100`.

~~~cypher
MATCH (a:QA001Account)
OPTIONAL MATCH (o:QA001Order)-[:QA001_BELONGS_TO]->(a)
RETURN a.accountId AS accountId, count(o) AS orderCount
ORDER BY accountId;
~~~

**Đáp án:** **10 record**, và mọi record có `orderCount = 10`. Việc `ORDER BY accountId` sắp xếp từ điển có thể cho thứ tự A1, A10, A2,..., nhưng điều đó **không thay đổi** số lượng đơn hàng; đừng dùng thứ tự từ điển này để suy ID số.

**Kiểm tra sau ghi:** chạy code mục 12 để đổi O42 thành `CONFIRMED`, rồi đọc qua một session có bookmark phù hợp. Kỳ vọng một record O42 có status mới; số order, account và relationship vẫn lần lượt 100/10/100.

## 17. Đo giới hạn một server: không chỉ nhìn throughput

Trước khi nâng cấp phần cứng hoặc thêm cluster, chạy load test trên **dữ liệu đủ lớn, gần thực tế**. Fixture 100 order chỉ đủ kiểm chứng câu Cypher và chuỗi công cụ, **không** đại diện cho hiệu năng production.

### 17.1. Xác định bốn workload

1. **Point lookup:** tìm một `QA001Order` bằng ID, đọc các property.
2. **Traversal:** từ account đến nhiều order, filter/sort/limit.
3. **Write transaction:** tạo/cập nhật đơn hàng và relationship theo business key.
4. **Mixed workload:** ví dụ giả định 80% đọc, 20% ghi, có số request đồng thời giống sản xuất.

Đo từng workload riêng trước, rồi đo hỗn hợp. Đảm bảo các request đọc về **đúng dữ liệu**, các transaction ghi **commit**, và không lẫn kết quả từ fixture cũ.

### 17.2. Thiết kế test có kiểm soát

- Cố định phiên bản Neo4j/Driver, size graph, schema/index/constraint, loại storage và số client.
- Đặt test load generator **ngoài máy Neo4j** để không làm số CPU/memory server bị sai do chương trình tạo tải.
- Warmup pool/JIT/page cache trước một nhóm phép đo steady-state; ghi riêng kết quả cold-ish.
- Tăng concurrency từng bước: 1 → 2 → 4 → 8 → 16, giữ cùng thời lượng/target request rate.
- Ghi throughput **committed transactions/s**, p50/p95/p99, timeout, retries và trạng thái đúng của graph.
- Đồng thời theo dõi CPU, memory, page cache, GC, IOPS, durable write latency, lock contention, network.
- Dừng tăng tải khi SLO latency hoặc error budget không còn đáp ứng; không tối đa hóa throughput bằng cách bỏ qua lỗi.
- Lặp lại để tránh kết luận từ một lần chạy hoặc một thời điểm cache khác nhau.

### 17.3. Phân biệt cải thiện do query và do topology

So sánh:

| Phép thử | Giữ nguyên | Thay đúng một yếu tố |
|---|---|---|
| Trước/sau tạo index đúng | Query, dữ liệu, server | Index |
| Trước/sau tăng page cache | Query, graph, workload | Memory allocation |
| Một server mạnh hơn | Query, graph, workload | CPU/RAM/SSD |
| 3 primaries | Query, logical data, nguồn tải | Topology/fault tolerance; chi phí replication |
| 3 primaries + secondaries | Query, data, writer primaries | Số bản sao có thể nhận query đọc |

Không diễn giải “3 primaries + 2 secondaries đạt nhiều read queries/s hơn” thành “mỗi write transaction nhanh hơn”. Cần tách **write throughput**, **read throughput**, **latency** và **tolerance of failures**.

## 18. Kiểm thử HA và failover trên staging

Một hệ thống được quảng cáo HA cần trải qua **diễn tập có kiểm soát**, không chỉ xem sơ đồ ba server.

### 18.1. Trước diễn tập

1. Xác định database/cluster staging, topology thực, các failure domains và người phê duyệt.
2. Đảm bảo backup có thể restore, baseline dữ liệu đúng và có phương án dừng diễn tập.
3. Bật metrics từ client (availability/latency/retries) và cluster (writer/quorum/lag).
4. Tạo luồng request đọc/ghi giả lập **có ID duy nhất và đáp án kiểm chứng**.
5. Ghi writer ban đầu, số primaries khỏe, trạng thái các secondaries.

### 18.2. Kịch bản mất một primary

Trên môi trường **được phép gây lỗi**:

- Ngừng đúng **một server/primary** bằng công cụ điều phối staging; không dùng production, không ngắt cả AZ thật.
- Ghi thời điểm phát hiện lỗi, thay đổi writer nếu cần, khoảng request bị timeout và số lần retry.
- Xác minh **hai primary còn lại** duy trì quorum cho database với topology 3 primaries.
- Kiểm tra các giao dịch báo commit thành công vẫn tồn tại và không tạo đơn hàng trùng do retry.
- Đưa server về trạng thái vận hành theo runbook, đo thời gian catch-up và quay lại mức fault tolerance bình thường.

**Không** tùy tiện thử dừng primary thứ hai trong cluster ba primary nếu bài test không có kế hoạch quan sát mất quorum và rollback an toàn. Việc “ứng dụng không ghi được” sau mất quorum là hệ quả bảo vệ nhất quán, không tự động là lỗi implementation.

### 18.3. Kịch bản mất secondary

- Dừng một secondary trong staging.
- Kiểm tra write SLI không bị ảnh hưởng đáng kể chỉ vì mất một secondary, trong khi read capacity có thể giảm.
- Theo dõi routing, replica catch-up và độ trễ khi secondary trở lại.
- Thử read-after-write có bookmark với một workflow thực, tránh kết luận từ số đọc cũ không có causal context.

### 18.4. Tiêu chí PASS

Không đủ để nói “cluster tự bầu leader”. Cần chứng minh:

- Tỷ lệ request đọc/ghi thành công đáp ứng mục tiêu đã định.
- Thời gian gián đoạn/khôi phục nhỏ hơn error budget và RTO thử nghiệm.
- Không mất dữ liệu đã commit trong phạm vi cam kết kiểm thử.
- Retry không tạo side effects ngoài graph hoặc record trùng.
- Quorum và số bản sao khỏe được khôi phục; không duy trì nhiều giờ ở trạng thái chỉ còn chịu được 0 lỗi.
- Backup/restore còn hoạt động và alert gửi tới đúng người trực ca.

## 19. Một phương án thiết kế minh họa và các đánh đổi

Một dịch vụ graph **giả định** có yêu cầu:

- 4.000 read requests/s vào giờ cao điểm.
- 350 write transactions/s, cần trả kết quả trong vài trăm mili giây.
- Write availability SLO 99,95% trong 30 ngày.
- Chịu được mất **một server** mà không cần can thiệp thủ công để khôi phục writer.
- Có yêu cầu read-after-write cho luồng tạo đơn hàng.

Một lộ trình thiết kế có thể là:

1. Tối ưu Cypher, schema và Driver trước; đo khả năng một server thực sự.
2. Vì bắt buộc chịu lỗi một primary, chọn **topology ba primaries** trên failure domains độc lập, đủ CPU/RAM/disk để hai thành viên còn lại xử lý tải khi một thành viên mất.
3. Đo read throughput trên primaries; nếu quá tải đọc, **thêm secondaries** theo số liệu thay vì cấu hình sẵn thật nhiều.
4. Dùng `neo4j+s://`, `executeRead/executeWrite`, tên database tường minh và bookmarks cho các workflow cần causal consistency.
5. Tổ chức backup riêng, cảnh báo replication lag/quorum, diễn tập failover và theo dõi error budget.
6. Nếu writer CPU/locks/IOPS chạm trần ngay cả sau tối ưu, phân tích khả năng phân chia miền dữ liệu/workload; **không** trông đợi thêm primary làm một database có nhiều writer.

**Đây là ví dụ thiết kế, không phải sizing được bảo đảm.** Một cluster ba primaries có thể vẫn không đủ tải khi một thành viên lỗi; phải **đo degraded-mode capacity**, không chỉ đo khi cả ba khỏe.

## 20. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu chính xác |
|---|---|
| “Một server SSD rất nhanh là HA.” | SSD giải quyết latency/capacity, không loại lỗi process/host/AZ. |
| “Hai primaries đủ để chịu một lỗi và vẫn ghi.” | Majority của 2 cần 2; mất một là mất quorum ghi. |
| “Thêm secondary là thêm writer.” | Secondary chủ yếu đọc và replicate bất đồng bộ, không tham gia quorum ghi. |
| “Ba primaries giúp ghi nhanh gấp ba.” | Với mỗi database thông thường có một writer, còn replication/quorum tạo overhead. |
| “Cả cluster có một leader duy nhất.” | Leader/writer là **theo database**, nên nhiều database có thể có leader khác nhau. |
| “Read replica luôn thấy dữ liệu mới nhất.” | Secondary có thể lag; dùng bookmark khi cần quan hệ nhân quả. |
| “Quorum hoạt động nghĩa là không có downtime.” | Bầu leader, routing, timeout/retry vẫn có thể tạo khoảng gián đoạn. |
| “Thêm client càng nhiều càng nhanh.” | Khi bão hòa, p95/p99, queue và retry thường tăng, throughput chững. |
| “Replication thay backup.” | Xóa nhầm và lỗi logic có thể replicate; cần backup/restore độc lập. |
| “`SHOW SERVERS` khỏe nghĩa là SLO đạt.” | SLO phải đo bằng kết quả/latency của workload nghiệp vụ. |
| “Neo4j trên 3 containers Community thành cluster HA.” | Cluster/quorum là tính năng edition/deployment hỗ trợ, không phải số container. |
| “Khi dataset quá lớn, tăng primaries sẽ tự phân mảnh graph.” | Primaries là bản sao một database; phân vùng/sharding là kiến trúc khác. |

## 21. Bài tập có đáp án

### Bài 1 — Quorum

Một database có ba primaries. Nếu một primary lỗi nhưng hai primary còn lại khỏe và liên lạc được, database có thể duy trì write quorum không?

**Đáp án:** Có. Quorum là `floor(3/2)+1=2`; hai primaries còn lại đủ đa số. Có thể có khoảng gián đoạn khi bầu writer/định tuyến lại.

### Bài 2 — Hai primaries

Một database có hai primaries trên hai máy riêng. Mất một máy còn khả năng commit ghi theo quorum không?

**Đáp án:** Không. Quorum của hai primaries là 2; một bản sao còn lại không đủ đa số.

### Bài 3 — Secondaries

Một database có một primary và ba secondaries. Khi primary hỏng, liệu ba secondaries có tự bảo đảm HA ghi không?

**Đáp án:** Không. Read availability có thể còn tùy trạng thái dữ liệu/network, nhưng secondaries không tham gia nhóm primary để bầu writer. Muốn chịu lỗi primary ghi cần topology nhiều primaries đúng quy trình.

### Bài 4 — SLO 99,9%

Nếu mục tiêu availability đo theo thời gian là 99,9% trong 30 ngày, error budget tương đương bao nhiêu phút?

**Đáp án:** `43.200 × (1-0,999) = 43,2 phút`, tức 43 phút 12 giây.

### Bài 5 — Giới hạn server

Trong phép đo giả định, tăng worker từ 4 lên 8 không tăng throughput, p95 tăng từ 105 lên 240 ms và retry tăng. Nên tăng worker tiếp không?

**Đáp án:** Không nên mặc định. Cần quan sát CPU, lock contention, I/O, queue depth và pool; ưu tiên xử lý nút thắt và đặt giới hạn concurrency.

### Bài 6 — Bookmark

Request A ghi đơn hàng thành công, request B ngay sau đó đọc trên một secondary khác nhưng không thấy đơn. Có thể giải thích và sửa thế nào?

**Đáp án:** Secondary có thể chưa nhận transaction. Truyền bookmark hoặc dùng BookmarkManager trong workflow cần read-after-write để bảo đảm causal consistency, đồng thời đo chi phí chờ.

### Bài 7 — Đáp án fixture

Fixture tạo 10 account, 100 order có `amount=1..100` và 100 relationship. Tổng amount là bao nhiêu? Mỗi account có bao nhiêu order?

**Đáp án:** `sum(amount)=5050`, mỗi account có **10 order**. A1 có O1/O11/.../O91, A10 có O10/O20/.../O100.

### Bài 8 — Scale-up hay cluster?

Một hệ thống đơn máy còn dư CPU/RAM nhưng có yêu cầu “mất một host vẫn tiếp tục ghi”. Nên chỉ nâng lên máy mạnh hơn không?

**Đáp án:** Không. Yêu cầu này là fault tolerance, không phải thiếu capacity. Cần mô hình nhiều primaries trên failure domains độc lập cùng routing và failover test; vẫn phải sizing cho degraded mode.

### Bài 9 — Writer bottleneck

Một database cluster có ba primaries, writer bị lock contention trên một node cập nhật liên tục. Thêm hai primary nữa có chắc tăng write throughput không?

**Đáp án:** Không. Một writer xử lý ghi cho database; thêm primary có thể tăng replication/quorum overhead. Phải xem mô hình truy cập/khóa, batch, index và phương án phân chia workload.

### Bài 10 — Backup và HA

Một thao tác Cypher nhầm lẫn xóa hàng nghìn relationship và được commit/replicate tới toàn cluster. Cluster có tự đưa graph về trạng thái trước khi xóa không?

**Đáp án:** Không. Replication truyền cả thay đổi hợp lệ nhưng sai nghiệp vụ. Cần backup/restore, point-in-time strategy theo edition và quy trình phê duyệt/kiểm toán.

## 22. Checklist quyết định kiến trúc

Trước khi quyết định dùng một server hay cluster, nhóm kỹ thuật cần thống nhất:

- [ ] Định nghĩa riêng read/write availability SLI, latency threshold, SLO và error budget.
- [ ] Xác định RPO/RTO và tình huống lỗi cần chịu (process, host, AZ, data center).
- [ ] Biết edition/version thực và các lựa chọn topology/managed service được hỗ trợ.
- [ ] Có benchmark một máy đo CPU, RAM, I/O, locks, network, p95/p99 theo workload thật.
- [ ] Có dữ liệu về read/write ratio và mức đồng thời, không dựa vào tổng node đơn thuần.
- [ ] Kiểm chứng query/index/batch trước khi quy mọi chậm trễ cho phần cứng.
- [ ] Nếu cần write HA, thiết kế quorum primaries trên failure domains độc lập.
- [ ] Nếu cần read scale, thêm secondary theo dữ liệu và có metrics replication lag.
- [ ] Driver dùng routing URI, read/write transaction methods và database đúng.
- [ ] Có bookmark policy cho workflow yêu cầu causal consistency.
- [ ] Có kế hoạch capacity khi **một primary mất**, không chỉ trong điều kiện khỏe.
- [ ] Có backup/restore đã diễn tập và test failover trên staging.
- [ ] Có alert quorum, writer/election, transaction lag, disk pressure và client error budget.
- [ ] Có phương án rollback khi thay topology/upgrade/scale mà không dùng lệnh phá hủy ngẫu nhiên.

## 23. Dọn fixture trên database thực hành

Chỉ chạy trên **database test** đã dùng, sau khi hoàn tất đối soát và phép thử. Không chạy nếu nhãn `QA001Account` hoặc `QA001Order` đang thuộc dữ liệu sản xuất.

~~~cypher
MATCH (n)
WHERE n:QA001Account OR n:QA001Order
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa001_account_id IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa001_order_id IF EXISTS;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA001Account OR n:QA001Order
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining = 0`. Không dùng cleanup này để mô phỏng cluster failover hay backup; nó chỉ xóa dữ liệu thử nghiệm.

## 24. Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Introduction to clustering](https://neo4j.com/docs/operations-manual/current/clustering/introduction/): server/database topology, primaries, secondaries, quorum và fault tolerance.
- [Neo4j Operations Manual — Leadership, routing and load balancing](https://neo4j.com/docs/operations-manual/current/clustering/setup/routing/): Raft leader, client/server routing và vai trò theo database.
- [Neo4j Operations Manual — Deploy a basic cluster](https://neo4j.com/docs/operations-manual/current/clustering/setup/deploy/): yêu cầu topology và cấu hình ví dụ.
- [Neo4j Operations Manual — Managing servers](https://neo4j.com/docs/operations-manual/current/clustering/servers/): health, enable/cordon/deallocate và metadata server.
- [Neo4j Operations Manual — Scaling with Neo4j](https://neo4j.com/docs/operations-manual/current/scalability/scaling-with-neo4j/): scale-up, read scaling, federation/sharding và giới hạn từng phương án.
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/): writer/leader, last committed transaction và các chỉ số cluster.
- [Neo4j Operations Manual — Cluster monitoring endpoints](https://neo4j.com/docs/operations-manual/current/clustering/monitoring/endpoints/): kiểm tra quorum, Raft lag và trạng thái các members.
- [Neo4j Java Driver Manual — Coordinate parallel transactions](https://neo4j.com/docs/java-manual/current/bookmarks/): bookmarks và causal consistency giữa các session.
- [Neo4j Java Driver Manual — Connect](https://neo4j.com/docs/java-manual/current/connect/): routing URI, xác thực và vòng đời Driver.
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/): các phương án phục hồi độc lập với HA replication.

**Ghi nhớ:** Một server có thể được **tối ưu hiệu năng** bằng CPU/RAM/page cache/SSD và Cypher tốt, nhưng không loại được điểm lỗi chung. Muốn **HA ghi** cho một database Neo4j Enterprise, hãy hiểu **writer, primaries và quorum**; muốn **mở rộng đọc**, dùng secondaries và giám sát độ trễ đồng bộ. **Thêm máy không tự làm một transaction hoặc một database có nhiều writer.** Thiết kế đúng phải bắt đầu từ read/write SLO, giới hạn tài nguyên và phép thử failover thực tế, sau đó kiểm chứng bằng số liệu thay vì giả định.
