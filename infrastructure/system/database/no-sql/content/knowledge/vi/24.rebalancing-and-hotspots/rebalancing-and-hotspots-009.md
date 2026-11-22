# Chi phí truyền dữ liệu, lưu tạm và tải nền khi cân bằng

## 1. Vì sao “thêm node để giảm tải” đôi khi làm hệ thống chậm đi?

Một cụm NoSQL có 6 node, dung lượng dữ liệu sử dụng đang tăng nhanh. Đội vận hành thêm 2 node để giảm dung lượng trung bình và chuyển bớt những phân mảnh nóng. Thế nhưng trong thời gian cân bằng, dashboard xuất hiện các hiện tượng:

- Network của node nguồn tăng vọt.
- Node đích ghi đĩa liên tục, dung lượng trống giảm nhanh.
- p99 của truy vấn người dùng tăng, dù CPU trung bình còn thấp.
- Compaction và replication lag tăng.
- Cache hit rate giảm ở những phân mảnh vừa di chuyển.
- Một số yêu cầu ghi bị timeout hoặc bị giới hạn tốc độ.
- Công việc chuyển dữ liệu tiếp tục sau khi bảng điều khiển báo “đã thêm node”.

Điều này không mâu thuẫn. **Cân bằng (rebalancing) chính là một workload lớn chạy trên hệ đang phục vụ người dùng.** Nó cần đọc dữ liệu từ vị trí cũ, chuyển qua mạng, ghi dữ liệu ở vị trí mới, bắt kịp thay đổi mới, sửa metadata định tuyến và dọn dữ liệu cũ. Với hệ có nhiều replica, index, log và cơ chế chống lỗi, tổng công việc có thể lớn hơn nhiều dung lượng logic được chuyển.

Ví dụ:

~~~text
Dữ liệu logic dự kiến di chuyển: 400 GiB
Nguồn vẫn nhận 8.000 write/s trong lúc chuyển.
Đích cần tạo lại một số index/cache.
Storage đang chạy compaction và backup.
Hai node nằm ở availability zone khác nhau.
~~~

Không thể dùng phép tính `400 GiB / tốc độ danh nghĩa của NIC` để cam kết thời gian chuyển hay chi phí cloud. Phải tính đến **băng thông hữu dụng, I/O đọc/ghi, write amplification, lưu tạm, các thao tác nền và rủi ro khi chuyển quyền sở hữu**.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Phân biệt **rebalance, reshard, bootstrap, replica relocation, hotspot mitigation**.
2. Lập bản đồ các giai đoạn và dữ liệu được đọc/ghi trong một cuộc di chuyển.
3. Ước lượng chi phí network, I/O, dung lượng tạm, CPU và các tác vụ hậu chuyển.
4. Giải thích vì sao replication factor, CDC/WAL, compaction và index làm chi phí lớn hơn dữ liệu logic.
5. Tính thời gian thấp nhất, thời gian khả thi và ngân sách băng thông bằng đơn vị rõ ràng.
6. Thiết kế throttling/backpressure để giữ SLO người dùng trong lúc cân bằng.
7. Nhận biết khi nào dữ liệu cân bằng mà **tải vẫn lệch** vì hot key hoặc hot partition.
8. Xác định điều kiện cutover an toàn, rollback, recovery và quan sát.
9. Hiểu sự khác biệt của MongoDB, Cassandra, Elasticsearch/OpenSearch, Redis Cluster và dịch vụ NoSQL managed.
10. Lập kế hoạch vận hành và kiểm thử cân bằng trong môi trường an toàn.

---

## 2. Cân bằng gì, trên đơn vị nào?

Không nên đồng nhất tất cả thao tác dưới từ “move data”.

| Hoạt động | Mục đích | Đơn vị thường liên quan | Công việc có thể phát sinh |
|---|---|---|---|
| **Rebalance** | Phân bổ lại dữ liệu/tải giữa các node | Shard, chunk, tablet, token range | Copy/stream, placement update |
| **Reshard / repartition** | Thay cách gán key vào phân mảnh | Shard-key range hoặc partition | Đọc và ghi lại dữ liệu, đổi routing |
| **Replica relocation** | Chuyển một bản sao sang node mới | Replica của shard/partition | Full copy + catch-up |
| **Bootstrap** | Thêm node tham gia lưu dữ liệu | Token ranges / partitions | Streaming nhiều nguồn |
| **Decommission** | Rút node khỏi cụm | Những phần node đang chịu trách nhiệm | Chuyển dữ liệu tới các node khác |
| **Repair / anti-entropy** | Khôi phục hội tụ giữa replica | Range, partition, SSTables | So sánh, truyền bản còn thiếu |
| **Compaction** | Sắp xếp, hợp nhất file lưu trữ | SSTable/segment | Đọc và ghi lại nhiều byte |
| **Hotspot mitigation** | Giảm điểm nóng CPU/IOPS/QPS | Key, tenant, range, shard | Split/redistribute hoặc đổi mô hình tải |

Một operation có thể kích hoạt nhiều loại công việc. Ví dụ thêm node làm rebalance, dữ liệu được stream đến node mới, sau đó compaction chạy và cache dần được làm nóng.

### 2.1. Phân biệt shard và replica

Giả sử một shard logic có replication factor \(RF=3\):

~~~text
Logical shard S42:
  Replica S42-A on node A
  Replica S42-B on node B
  Replica S42-C on node C
~~~

Nếu chuyển một replica từ C sang D, dữ liệu cần sao chép có thể là **kích thước một bản replica**, không nhất thiết là kích thước của cả ba bản.

Nếu thay shard key và viết lại một dataset rộng, hệ có thể phải xử lý **phần lớn dữ liệu logic** và xây lại nhiều replica theo giao thức. Vì vậy phải mô tả **đơn vị chuyển thực tế** trước khi nhân với RF.

### 2.2. Dung lượng logic khác dung lượng lưu trữ vật lý

Một tập dữ liệu có thể được báo:

~~~text
Uncompressed logical data: 600 GiB
Compressed stored data:    270 GiB
Index and metadata:         90 GiB
WAL/commit log:             18 GiB
Snapshot/temporary files:   60 GiB
~~~

Không được cộng/trừ các con số tùy ý. Tùy engine, chỉ số “data size” có thể đã bao gồm hoặc chưa bao gồm index, tombstone, replication và compressed bytes. **Nguồn metric và đơn vị phải được ghi cạnh mỗi số.**

---

## 3. Đường đi của một lần chuyển dữ liệu

Một kế hoạch rebalance an toàn thường có nhiều giai đoạn logic:

~~~mermaid
flowchart TD
    A["Chọn shard/range cần chuyển"] --> B["Kiểm tra capacity và failure domains"]
    B --> C["Chuẩn bị đích và snapshot/checkpoint"]
    C --> D["Copy/stream dữ liệu nền"]
    D --> E["Catch up các write mới"]
    E --> F["Kiểm tra trạng thái và điều kiện chuyển quyền"]
    F --> G["Cutover routing/ownership"]
    G --> H["Theo dõi ổn định, cache warm-up"]
    H --> I["Cleanup bản cũ và dữ liệu tạm"]
~~~

Tên giai đoạn không phải tên API dùng chung cho mọi DBMS. Engine khác nhau có thể dùng streaming, snapshot, log replay hoặc cơ chế dual-read/dual-write riêng. **Không tự triển khai cutover chỉ từ sơ đồ này.**

### 3.1. Prepare và placement

Hệ chọn nguồn, đích, những replica có sẵn và failure domain để không vô tình đặt các bản sao của cùng shard ở một vùng lỗi.

Chi phí: metadata, kiểm tra placement, reserve capacity, tạo partition/segment, khởi tạo kết nối và có thể ảnh hưởng routing.

### 3.2. Initial copy

Node nguồn đọc dữ liệu tại một mốc hoặc qua luồng được engine xác định; node đích ghi bản ban đầu.

Chi phí: source disk read, network egress/ingress, destination disk write, CPU compression/encryption/checksum và bộ đệm.

### 3.3. Catch-up

Trong lúc chuyển, các request foreground vẫn tạo write mới. Đích phải nhận các thay đổi xảy ra sau mốc snapshot theo cơ chế của hệ.

Chi phí: log/CDC/replication traffic, WAL, backlog, bộ nhớ, disk và latency. Nếu write rate lớn hơn tốc độ catch-up, quá trình có thể không kịp hội tụ.

### 3.4. Validate và cutover

Cần một quy tắc rõ để xác định đích đã đủ điều kiện phục vụ, tránh mất hoặc nhân đôi write khi đổi owner/routing.

Chi phí: synchronization, quorum/metadata update, tạm chặn một số thao tác hoặc thêm round-trip trong một số thiết kế.

### 3.5. Cleanup

Nguồn cũ có thể tiếp tục giữ bản dư một thời gian nhằm bảo vệ recovery/rollback; sau đó engine mới thu hồi dung lượng. File bị xóa ở tầng logic không nhất thiết khiến dung lượng storage giảm ngay do snapshot, compaction, retention hoặc segment lifecycle.

**Mốc “routing đã đổi” không đồng nghĩa tất cả chi phí background đã kết thúc.**

---

## 4. Nhìn đầy đủ luồng dữ liệu và tài nguyên

~~~mermaid
flowchart LR
    C["Foreground clients"] --> S["Node nguồn"]
    C --> T["Node đích"]
    S -->|"Snapshot / stream"| N["Network"]
    N -->|"Copy"| T
    S -->|"Changes after snapshot"| L["Replication / change log"]
    L --> T
    S --> D1["Source disk reads"]
    T --> D2["Destination writes"]
    T --> C2["Compaction / index / cache"]
    M["Cluster metadata"] --> S
    M --> T
~~~

Ngay cả khi dữ liệu chỉ “đi từ S sang T”, những tài nguyên sau có thể chịu tải:

- **Source:** disk read bandwidth, CPU decompress/checksum, outgoing network, cache eviction.
- **Destination:** incoming network, disk write IOPS/throughput, WAL, index build, compaction và cache warming.
- **Coordinator/control plane:** routing metadata, migration coordination, lease/epoch state.
- **Các replica khác:** đồng bộ theo placement/replication rule, repair hoặc backfill.
- **Ứng dụng:** reconnect, redirect, retry, tăng tail latency khi route thay đổi.
- **Hạ tầng:** cross-zone network, volume snapshots, object storage, logging, monitoring.

### 4.1. Resource contention có thể không đối xứng

Một node nguồn có disk đọc chậm trong khi node đích có disk ghi nhanh. Tăng băng thông mạng không cải thiện throughput vì bottleneck là **source read**.

Ngược lại, đích đang chạy compaction mạnh có thể khiến queue ghi và fsync latency tăng; source vẫn rảnh mà migration bị chậm.

### 4.2. Dữ liệu di chuyển giữa những miền lỗi khác nhau

Cross-AZ hoặc cross-region có thể chịu:

- RTT cao hơn.
- Thông lượng hữu dụng khác.
- Giá truyền dữ liệu tính theo chính sách nhà cung cấp.
- Ảnh hưởng của packet loss và retry.
- Yêu cầu mã hóa và compliance.

Phải kiểm tra **giá hiện hành và topology thật** của nhà cung cấp trước khi đưa ra dự toán tiền; không dùng một giá egress cố định cho mọi cloud.

---

## 5. Chi phí thứ nhất: số byte thực sự phải truyền

Gọi:

- \(B_{\text{logical}}\): số byte dữ liệu logic thuộc phần cần chuyển.
- \(B_{\text{copy}}\): byte thực sự được gửi trong pha copy ban đầu.
- \(B_{\text{delta}}\): byte thay đổi được gửi trong catch-up.
- \(B_{\text{retry}}\): byte gửi lại do retry/restart/verification.
- \(B_{\text{aux}}\): metadata, index, checksum hoặc traffic phụ khác được gửi qua mạng.

Một cách lập ngân sách:

\[
B_{\text{network,total}}
\approx
B_{\text{copy}}+B_{\text{delta}}+B_{\text{retry}}+B_{\text{aux}}.
\]

Không được mặc nhiên:

\[
B_{\text{network,total}}=B_{\text{logical}}.
\]

### 5.1. Compression

Nếu 1 TiB dữ liệu logic được nén thành 420 GiB ở storage, dữ liệu truyền thực có thể gần kích thước nén hoặc khác tùy streaming protocol. Một số hệ truyền SSTable/segment đã nén; hệ khác decode và re-encode.

Vì vậy trong ước lượng cần biết **metric đọc từ engine là compressed-on-disk bytes hay uncompressed logical bytes**.

### 5.2. Replication factor

Giả sử một shard logic 200 GiB với RF=3, đang có ba replica. Nếu chỉ **relocate một replica** tới node khác, có thể cần chuyển một bản khoảng 200 GiB trước overhead.

Không được tự nhân \(200\times3\) nếu kế hoạch chỉ tạo **một** replica mới. Ngược lại, một thao tác rebuild/repartition có thể cần chép nhiều bản, khi đó nhân số bản thực tế phải tạo là hợp lý.

Công thức có ý nghĩa khi xác định được các bản mới:

\[
B_{\text{baseline}}
=\sum_{\text{new copies }j} B_j.
\]

### 5.3. Retry và restart

Nếu đã chuyển 70% rồi job thất bại, engine có thể tái sử dụng dữ liệu đã chuyển, hoặc phải gửi lại một phần tùy checkpoint/protocol.

Do đó `retry overhead=0` thường là giả định quá lạc quan cho capacity planning, nhưng cũng không nên mặc định mọi retry copy lại từ đầu.

### 5.4. Checksum và metadata

Hash/checksum có thể tăng CPU và một số network traffic. Một số hệ so sánh digest trước khi quyết định gửi nội dung, có thể giảm lượng truyền nhưng vẫn cần đọc disk/CPU để tính digest.

### 5.5. Write delta

Nếu phần dữ liệu đang di chuyển vẫn nhận 50 MiB/s thay đổi logic, catch-up cần truyền hoặc tái áp dụng những thay đổi đó. Chênh lệch giữa logical write rate và log/replication bytes phụ thuộc amplification/encoding của hệ.

Ví dụ copy kéo dài 30 phút:

\[
B_{\text{changed,logical}}
=50\text{ MiB/s}\times1800\text{ s}
=90\,000\text{ MiB}\approx87.9\text{ GiB}.
\]

Đây là **dữ liệu thay đổi logic giả định**, chưa phải chính xác bytes log gửi qua mạng.

---

## 6. Chi phí thứ hai: thời gian chuyển theo bottleneck thực

Cho một bản cần chuyển \(B\) byte với tốc độ hữu dụng \(v\) byte/giây:

\[
T_{\min}\ge\frac{B}{v}.
\]

Nhưng \(v\) thường bị giới hạn bởi tài nguyên chậm nhất:

\[
v_{\text{effective}}
\le
\min(
v_{\text{source-read}},
v_{\text{network}},
v_{\text{destination-write}},
v_{\text{throttle}},
v_{\text{CPU-path}}
).
\]

Các đại lượng phải được quy đổi cùng đơn vị, với tốc độ CPU-path thể hiện số byte có thể xử lý mỗi giây.

### 6.1. Ví dụ 600 GiB

Giả sử phải stream **600 GiB** dữ liệu vật lý, một luồng có băng thông hữu dụng 150 MiB/s:

\[
B=600\times1024=614\,400\text{ MiB}.
\]

\[
T_{\min}=\frac{614400}{150}
=4096\text{ s}
\approx68.3\text{ phút}.
\]

Đây là **cận dưới cho pha copy trong giả định dòng truyền liên tục**; chưa gồm catch-up, compaction, checkpoint, retry và cutover.

### 6.2. Đừng lấy 10 Gbps làm tốc độ copy mặc định

10 Gbps danh nghĩa có tốc độ bit gần:

\[
10^{10}\text{ bit/s}/8
=1.25\times10^9\text{ byte/s}.
\]

Nhưng TCP/TLS overhead, shared network, CPU, storage, throttle và traffic foreground khiến tốc độ dùng riêng cho migration có thể thấp hơn nhiều.

Cũng phải phân biệt `GB` (hệ thập phân) và `GiB` (hệ nhị phân):

\[
1\text{ GiB}=2^{30}\text{ byte},\qquad
1\text{ GB}=10^9\text{ byte}.
\]

### 6.3. Song song nhiều job

Nếu chạy 4 job, mỗi job được cấu hình 150 MiB/s, điều đó **không chứng minh tổng đạt 600 MiB/s**. Chúng có thể chia chung một NIC, cùng disk hoặc cùng storage controller.

Phải xem giới hạn **theo node, theo link, theo volume và theo cluster**. Tăng concurrency vượt một mức có thể gây queue và làm thời gian tổng **dài hơn**.

### 6.4. Tốc độ delta và điều kiện hội tụ

Đặt:

- \(r\): tốc độ thay đổi cần catch-up (MiB/s thực tế sau encoding).
- \(c\): tốc độ catch-up có thể xử lý (MiB/s).

Nếu \(c\le r\), backlog không giảm về 0 khi workload giữ nguyên, trừ khi hệ dùng biện pháp khác như pause writes, thay đổi policy, bổ sung capacity hoặc chọn mốc cutover theo protocol.

Với backlog ban đầu \(D\), nếu \(c>r\) ổn định:

\[
T_{\text{catchup}}\approx\frac{D}{c-r}.
\]

Ví dụ \(D=60\,000\) MiB, \(c=140\) MiB/s, \(r=80\) MiB/s:

\[
T_{\text{catchup}}\approx\frac{60000}{60}
=1000\text{ s}\approx16.7\text{ phút}.
\]

Phép tính đơn giản giả định tốc độ không đổi và không có churn/compaction làm thay đổi backlog.

---

## 7. Chi phí thứ ba: băng thông và tiền truyền dữ liệu

Một dự toán tài chính có thể phân nhóm:

~~~text
A. Trong cùng host/zone
B. Khác zone, cùng region
C. Khác region
D. Qua object storage hoặc network trung gian
E. Traffic replication bình thường
F. Traffic phát sinh riêng do migration
~~~

Không phải mọi byte được tính tiền giống nhau. Một số dịch vụ có miễn phí một chiều hoặc điều kiện đặc biệt; giá thay đổi theo region, loại dịch vụ và hợp đồng.

### 7.1. Công thức ngân sách tiền

Nếu một luồng truyền thuộc nhóm giá \(p\) tiền/GiB và có \(B\) GiB có tính phí:

\[
C_{\text{network}}=B\times p.
\]

Với nhiều nhóm:

\[
C_{\text{network,total}}
=\sum_i B_i p_i.
\]

Tính thêm nếu phù hợp:

- Object storage request/read cost.
- Snapshot export/import.
- Compute chạy lâu hơn.
- Storage volume tạm.
- Egress qua load balancer/NAT hoặc dịch vụ mạng liên quan.
- Backup/replication tăng trưởng trong thời gian cân bằng.

### 7.2. Ví dụ minh họa không gắn giá nhà cung cấp

Giả sử 700 GiB traffic có tính phí qua một ranh giới, đơn giá giả định **0,02 USD/GiB**:

\[
C=700\times0.02=14\text{ USD}.
\]

Đây chỉ là bài toán đơn vị; **không phải báo giá cloud hiện hành**.

### 7.3. Chi phí cơ hội còn quan trọng hơn hóa đơn

Dù truyền dữ liệu trong cùng AZ có thể rẻ về tiền, nó vẫn tiêu tốn network bandwidth khiến foreground request chậm. Chi phí vận hành bao gồm **latency, error budget, throttling, mất hiệu năng người dùng và thời gian đội vận hành**.

---

## 8. Chi phí thứ tư: lưu tạm trên node đích và node nguồn

Di chuyển an toàn thường không thể xóa bản nguồn ngay khi bắt đầu. Trong khoảng chồng lấn:

~~~text
Nguồn giữ bản cũ.
Đích đang giữ bản mới từng phần.
Log các thay đổi mới vẫn tăng.
Snapshots hoặc temporary segments còn được giữ.
~~~

Vì vậy cần **dung lượng đĩa trống vượt trên kích thước cuối cùng của dữ liệu**.

### 8.1. Mô hình headroom đĩa

Cho node đích:

- \(D_0\): dung lượng đang sử dụng trước migration.
- \(B_{\text{incoming}}\): byte sẽ được ghi tới node.
- \(B_{\text{temp}}\): file tạm/checkpoint/log/snapshot phát sinh.
- \(B_{\text{compaction}}\): đỉnh dung lượng cần khi compaction/rewrite.
- \(G\): tăng trưởng foreground dự kiến trong thời gian migration.
- \(H\): phần dung lượng phải để dự phòng an toàn theo policy.

Điều kiện lập kế hoạch:

\[
D_{\text{capacity}}
\ge D_0+B_{\text{incoming}}+B_{\text{temp}}
+B_{\text{compaction}}+G+H.
\]

**Không nên cộng cùng một byte hai lần** nếu metric thực tế đã bao gồm một hạng mục. Mục tiêu là liệt kê các loại byte và đỉnh đồng thời, không phải dùng công thức như số chuẩn của một engine.

### 8.2. Ví dụ 2 TiB node

~~~text
Dung lượng volume:                   2048 GiB
Đang sử dụng trước migration:        1150 GiB
Dữ liệu mới cần lưu trên node:        420 GiB
Temporary/log/checkpoint peak:        100 GiB
Compaction headroom peak:            180 GiB
Tăng trưởng foreground dự kiến:       30 GiB
Dự phòng vận hành đã chọn:           160 GiB
~~~

Tổng yêu cầu giả định:

\[
1150+420+100+180+30+160=2040\text{ GiB}.
\]

Kế hoạch chỉ còn **8 GiB margin** với các giả định ấy. Đây là tình huống rất mong manh: chỉ cần log/backfill/compaction lớn hơn dự kiến là có thể đầy volume. Dù phép tính vừa lọt 2 TiB, vận hành thực tế nên **xem xét lại kế hoạch**, tăng capacity hoặc giảm số job đồng thời.

### 8.3. Source cũng có chi phí lưu tạm

Node nguồn có thể giữ:

- Dữ liệu cũ tới khi cutover xác nhận.
- WAL hoặc changelog cần replay.
- File snapshot/backup đang được tham chiếu.
- Tombstone hay segment chưa được GC.
- File compaction phát sinh khi dữ liệu tiếp tục thay đổi.

Không được chỉ kiểm tra disk trống trên đích.

### 8.4. Dung lượng xóa không trở lại ngay

Sau khi logical owner đã chuyển, storage engine có thể dọn dữ liệu thông qua compaction/cleanup ở một thời điểm sau. Với snapshot hoặc filesystem copy-on-write, file đã “xóa” có thể vẫn được tham chiếu. Chỉ số disk usage có thể không giảm tức thời.

---

## 9. Compaction và write amplification

Nhiều NoSQL dùng cấu trúc LSM hoặc log-structured storage. Dữ liệu mới có thể được append vào log/memtable rồi flush thành SSTables; compaction hợp nhất hoặc viết lại SSTables để tối ưu đọc, xóa tombstone hoặc giảm số file.

### 9.1. Vì sao migration gây thêm compaction?

Node đích nhận một lượng lớn dữ liệu mới:

~~~text
Stream 400 GiB SSTable/data
  -> ghi vào storage
  -> cần điều chỉnh levels/segments
  -> compaction hoặc index work
  -> đọc lại và ghi lại một phần dữ liệu
~~~

Khối dữ liệu **được truyền một lần** vẫn có thể được **đọc/ghi nhiều lần** ở storage trong chu kỳ hoàn tất.

### 9.2. Write amplification

Một mô hình:

\[
WA=\frac{\text{physical bytes written}}{\text{logical bytes newly accepted}}.
\]

Nếu một workload tạo 100 GiB logical write nhưng engine ghi 400 GiB trong chu kỳ được đo, \(WA=4\). Định nghĩa và đo thực tế cần nêu các thành phần WAL, compaction, replication, snapshot có được tính hay không.

Trong rebalancing, không thể đơn giản lấy một WA trung bình của workload bình thường rồi coi là hệ số cố định cho mọi engine. **Streaming SSTables, ingest file, index rebuild và compaction có các đường khác nhau.**

### 9.3. Read amplification

Compaction có thể khiến đọc thêm nhiều file/level trong khi metadata/cache chưa ổn định. Node nguồn cũng mất page cache vì quét dữ liệu để stream.

Vì vậy latency read có thể tăng dù logical QPS không đổi.

### 9.4. IOPS và throughput

- Copy file lớn thường thiên về **sequential throughput**.
- Index rebuild có thể gây **random I/O**.
- Journal sync/foreground writes nhạy với **fsync latency**.
- Compaction có thể vừa đọc vừa ghi lượng byte lớn.

Một volume đạt 1 GiB/s tuần tự vẫn có thể quá tải bởi random IOPS hoặc latency deadline của write request. Cần đo cả **throughput và latency**, không chỉ MB/s.

---

## 10. CPU, bộ nhớ và cache cũng là chi phí di chuyển

### 10.1. CPU

Migration có thể cần:

- Compression/decompression.
- Encryption/TLS.
- Checksum/hash.
- Serialization và validation.
- Rebuild index hoặc query structures.
- Routing metadata, merge và bookkeeping.

Khi CPU đang phục vụ truy vấn foreground, chạy thêm các tác vụ này có thể tăng queueing delay ngay cả khi tổng CPU trung bình trông chưa đạt 100%.

### 10.2. Memory

Node nguồn và đích cần buffer để stream, track chunk, giữ replication backlog, xây index hoặc chạy compaction.

Tăng số job đồng thời có thể:

- Tăng heap/off-heap usage.
- Tăng GC pressure ở JVM-based engines.
- Làm giảm page cache có ích.
- Dẫn đến OOM hoặc backpressure đột ngột nếu tính thiếu buffer.

### 10.3. Cache pollution ở nguồn

Một full scan trên nguồn đọc nhiều block ít được ứng dụng dùng, đẩy block nóng khỏi OS page cache hoặc cache của DBMS.

Hiệu ứng:

~~~text
Trước migration:
  cache hit rate cao, read p99 thấp.

Trong migration:
  streaming đọc file lạnh, eviction tăng.

Sau migration:
  foreground read phải đọc disk nhiều hơn để warm lại.
~~~

### 10.4. Cold cache ở đích

Node đích có dữ liệu trên disk nhưng cache chưa được làm nóng. Nếu cutover một tenant nóng ngay, read p99 có thể xấu dù node còn CPU.

Một số hệ hỗ trợ prewarming, gradual routing, cache retention hoặc các chiến lược điều tiết; phải chọn phù hợp engine và không tạo tải thừa khi “warm” vô tội vạ.

### 10.5. Mức sử dụng trung bình không đủ

Để đánh giá ảnh hưởng, theo dõi:

- CPU saturation và runnable queue.
- Disk read/write latency.
- Disk queue depth.
- GC pause hoặc memory pressure.
- Cache hit rate/cache eviction.
- Network retransmit.
- Read/write p95/p99.
- Foreground timeout/retry rate.

---

## 11. Tải nền (background load) chồng lấn khi cân bằng

Không phải mọi tác vụ nền do migration trực tiếp sinh ra. Nhưng chạy **đồng thời** có thể tạo điểm nghẽn.

| Tác vụ nền | Vai trò | Tài nguyên thường dùng | Rủi ro khi chạy cùng rebalance |
|---|---|---|---|
| Compaction | Hợp nhất, làm sạch data files | Disk read/write, CPU, temporary space | Saturation, disk full |
| Repair / anti-entropy | Đồng bộ replica lệch | Network, disk scan, CPU | Tranh bandwidth |
| Backup / snapshot | Bảo vệ dữ liệu | Disk/network/object storage | Cạnh tranh I/O, giữ file cũ |
| Index build | Phục vụ truy vấn | CPU, disk, memory | Mất headroom |
| CDC / change stream | Chuyển thay đổi tới downstream | Log, network, queue | Lag và retention tăng |
| TTL cleanup / GC | Loại dữ liệu hết hạn | Compaction, metadata | Dọn dẹp bị trễ |
| Replica catch-up | Theo kịp nguồn | Network/disk/log | Migration không hội tụ |
| Rebuild materialized view | Đồng bộ read model | CPU, writes, network | Tăng amplification |
| Data validation | Checksum, compare | CPU và disk read | Foreground cache eviction |

### 11.1. Không nên tắt tất cả background tasks

Tắt repair/compaction/backup tùy tiện có thể làm rủi ro tăng:

- Tombstone hoặc file rác phình lên.
- Replica lệch lâu.
- Backup RPO vượt ngưỡng.
- Log retention tăng tới mức đầy disk.
- Read performance về sau xuống nghiêm trọng.

Cần **sắp lịch và điều tiết có hiểu biết**, không dùng một nút “disable background” như giải pháp chung.

### 11.2. Ngân sách tài nguyên là hữu hạn

Nếu node có 1000 MiB/s disk throughput hữu dụng trong điều kiện benchmark, foreground đang dùng 500 MiB/s, không nên mặc nhiên cấp 500 MiB/s còn lại cho migration. Cần chừa headroom cho burst, compaction, journal và sự biến động.

Một mô hình:

\[
v_{\text{migration,budget}}
\le
v_{\text{safe-capacity}}
-
v_{\text{foreground,peak}}
-
v_{\text{mandatory-background}}
-
v_{\text{reserve}}.
\]

Các tốc độ phải cùng đại lượng và cùng tài nguyên. Trong thực tế latency có thể phi tuyến khi gần saturation, nên throughput budget vẫn cần kiểm tra bằng p99/queue depth.

### 11.3. Ưu tiên foreground nhưng vẫn tiến triển

Nếu luôn ưu tiên foreground 100%, migration có thể không bao giờ hoàn tất khi traffic cao. Nếu ưu tiên migration quá mức, SLO người dùng bị phá.

Cần chính sách công bằng theo mục tiêu:

- Giữ foreground dưới ngưỡng latency/error.
- Cấp một mức băng thông tối thiểu nếu tình hình cho phép.
- Tự giảm migration khi p99/compaction backlog tăng.
- Có maintenance window hoặc deadline cho những shard phải chuyển trước khi rủi ro cao.

---

## 12. Backfill, WAL/CDC và vấn đề “đuổi theo mục tiêu đang chạy”

Một shard tiếp tục nhận writes trong lúc di chuyển. Snapshot ban đầu chỉ là ảnh tại một mốc; muốn đích có trạng thái hiện tại cần áp dụng delta.

~~~mermaid
sequenceDiagram
    participant Client
    participant Src as Source
    participant Log as WAL / change stream
    participant Dst as Destination

    Src->>Dst: Initial data copy at checkpoint K
    Client->>Src: Write event K+1
    Src->>Log: Record K+1
    Client->>Src: Write event K+2
    Src->>Log: Record K+2
    Log->>Dst: Replay K+1, K+2
    Dst-->>Src: Caught up to required point
    Src->>Dst: Cutover via engine protocol
~~~

Sơ đồ minh họa một họ thiết kế. Một số hệ không dùng WAL replay theo đúng cách này; có hệ sử dụng replication stream, CDC hoặc snapshot streaming và cơ chế riêng.

### 12.1. Thứ tự áp dụng delta

Nếu một key có:

~~~text
K+1: status = PENDING
K+2: status = PAID
~~~

Đích không được áp dụng K+2 rồi K+1 và cuối cùng để `PENDING` khi nguồn đã xác nhận `PAID`, trừ khi quy tắc version/conflict của hệ xử lý được. Cần engine protocol bảo toàn thứ tự hoặc version/causality trong phạm vi phù hợp.

### 12.2. Catch-up backlog

Nếu write rate tăng đúng lúc khuyến mại, backlog có thể tăng dù initial copy đã xong.

Metrics hữu ích:

~~~text
oldestUnappliedChangeAge
changeLogBytesPending
lastAppliedSequence
sourceCommitPoint
catchupBytesPerSecond
~~~

Tên metric thực tế phụ thuộc hệ. **Không lấy “percent data copied = 100%” làm bằng chứng đã cutover an toàn.**

### 12.3. Changelog retention

Nếu đích quá chậm, những log cần replay có thể bị xóa theo retention policy, buộc rebuild/copy lại theo giao thức. Khi thiết kế window, phải xem:

\[
T_{\text{copy}}+T_{\text{catchup}}
<
T_{\text{safe log retention}}
\]

trong điều kiện giả định liên quan. Không phải mọi hệ có một retention time cố định theo cách này, nhưng nguyên tắc là **log phải còn đủ lâu để đích bắt kịp**.

### 12.4. Dual-write không tự giải quyết

Một số migration ứng dụng sử dụng dual-write tới nguồn và đích. Điều này tạo nhiều failure mode:

- Nguồn thành công, đích lỗi.
- Đích thành công, nguồn timeout.
- Hai write cùng key đảo thứ tự.
- Retry tạo side effect trùng.
- Read chuyển quá sớm.
- Rollback không biết nguồn nào mới nhất.

Dual-write đòi idempotency, version/ordering, recovery và cutover contract; không thể thay thế bằng hai API calls nối nhau mà coi như transaction.

---

## 13. Cutover: chuyển quyền sở hữu không phải đổi một biến boolean

Đây là giai đoạn dễ gây lỗi correctness nếu tự quản sharding.

~~~text
Source owner: node A
Destination candidate: node D

Trước cutover: A có quyền phục vụ authoritative writes.
Sau cutover:  D có quyền phục vụ authoritative writes.
~~~

Nếu A và D đều tưởng mình là owner trong một khoảng, cùng key có thể bị ghi ở hai nơi mà không có ordering/merge hợp lệ.

### 13.1. Ownership epoch hoặc generation

Một thiết kế có thể sử dụng epoch tăng:

~~~text
epoch 51: A là owner
epoch 52: D là owner
~~~

Request mang epoch cũ bị từ chối/chuyển hướng theo protocol; metadata update phải có cơ chế nhất quán để tránh split-brain.

### 13.2. Fencing

Một owner cũ có thể bị pause rồi chạy tiếp sau khi lease/epoch hết hạn. **Fencing token** giúp hệ đích phát hiện và từ chối thao tác stale.

Không tự cho rằng TTL của lock khiến process cũ chắc chắn dừng.

### 13.3. Router stale

Client/route cache có thể còn giữ placement cũ. Cần biết DBMS xử lý:

- Redirect.
- Retry có kiểm soát.
- Refresh metadata.
- Không đọc/ghi vào owner đã mất quyền.
- Xử lý request đang chạy tại thời điểm chuyển.

Đừng hard-code địa chỉ node trong ứng dụng nếu database đã có routing layer được hỗ trợ.

### 13.4. Khi rollback

Nếu cần quay lại nguồn cũ sau cutover, phải xác định **dữ liệu mới đã ghi vào đích** sẽ được chuyển ngược thế nào, và bảo đảm không mất/đảo thứ tự.

Rollback một migration đã chuyển quyền không đơn giản là đổi routing về node A nếu A không còn theo kịp D.

### 13.5. Tính đầy đủ và xác thực

Tùy engine, có thể kiểm tra count, version/checksum, log position hoặc những validation markers trước/sau cutover.

Nhưng một checksum trên snapshot K không chứng minh đích đã có các write sau K. **Data validation phải gắn với consistency point/epoch cụ thể.**

---

## 14. Hotspot: cân bằng dung lượng không đồng nghĩa cân bằng tải

Một cluster có bốn shard, mỗi shard giữ 250 GiB:

~~~text
Shard A: 250 GiB,  500 QPS
Shard B: 250 GiB,  600 QPS
Shard C: 250 GiB,  700 QPS
Shard D: 250 GiB, 35.000 QPS
~~~

Về dung lượng, cụm **rất cân bằng**. Về workload, shard D là điểm nóng nghiêm trọng.

### 14.1. Data skew và workload skew

- **Data skew:** byte/partition count lệch.
- **Read skew:** một nhóm key nhận nhiều read.
- **Write skew:** một key/range nhận nhiều write.
- **CPU skew:** một query/index/compaction tốn CPU tập trung.
- **Network skew:** một node truyền/nhận nhiều traffic hơn.
- **Storage skew:** node có IOPS/latency cao dù byte sử dụng không lớn.

Quyết định rebalance chỉ dựa vào disk utilization có thể chuyển đúng dữ liệu **nhưng không chuyển đúng tải**.

### 14.2. Hot key không tự được giải bằng thêm node

Nếu 80% write tới một key duy nhất, hash partitioning vẫn đặt key ấy vào một owner/consensus group. Thêm node không chia được write tới cùng key mà không thay đổi mô hình concurrency hoặc phương thức phân bổ.

Các cách cân nhắc:

- Cache những read được phép stale.
- Sharded counters/escrow quota khi invariant cho phép.
- Partition theo sub-key/bucket có cơ chế merge.
- Coalesce/batch writes.
- Tách workload analytical.
- Đổi access pattern/index.
- Admission control/rate limit.

Mỗi phương án đổi complexity và consistency. Ví dụ sharded counter tăng throughput nhưng cần giải quyết tổng chính xác hoặc giới hạn cấp phát.

### 14.3. Di chuyển hot shard có thể chỉ đổi nơi nóng

Nếu chuyển shard D từ node 4 sang node 5, node 5 có thể ngay lập tức thành hotspot. Rebalance thành công về placement nhưng **chưa giảm tải của shard**.

### 14.4. Nên xét tải theo thời gian

Một shard nóng trong giờ cao điểm nhưng nguội ban đêm có thể khiến hệ rebalance qua lại nếu thuật toán quá nhạy.

Cần:

- Smoothing window.
- Hysteresis/threshold.
- Cooldown sau migration.
- Phân biệt tải thường trực và spike ngắn.
- Chi phí di chuyển so với lợi ích dự kiến.

---

## 15. Chọn đích chuyển: không chỉ chọn node ít dữ liệu nhất

Một thuật toán placement tốt có thể xét nhiều chiều:

| Tiêu chí | Câu hỏi |
|---|---|
| Free disk | Đích đủ chỗ sau peak temporary/compaction không? |
| CPU/Memory | Có đủ headroom cho cache, index và foreground không? |
| Network | Link source–destination có còn bandwidth không? |
| Disk IOPS | Đích có chịu nổi writes + compaction không? |
| Hot workload | Chuyển shard vào đích có tạo điểm nóng mới? |
| Failure domain | Các replica cùng shard có bị gom vào một zone/rack? |
| Tenant isolation | Có vi phạm giới hạn workload/placement? |
| Data residency | Có được phép chuyển dữ liệu qua region/quốc gia? |
| Maintenance | Node đích có sắp restart/upgrade? |
| Routing locality | Người dùng ở đâu, RTT có đổi nhiều không? |
| Recovery | Nếu chuyển thất bại, có còn bản an toàn? |
| Cost | Network/storage/compute phát sinh chấp nhận được không? |

### 15.1. Replication factor không thay thế topology

RF=3 nhưng cả ba bản nằm cùng một failure domain không bảo vệ tốt khi domain đó hỏng. Rebalance cần duy trì các ràng buộc placement của engine.

### 15.2. Đích “trống” có thể không khỏe

Một node vừa khởi động có ít dữ liệu nhưng cache lạnh, đang rebuild index hoặc disk có latency bất thường. Chọn nó làm nơi nhận quá nhiều shard cùng lúc có thể làm sự cố nghiêm trọng hơn.

### 15.3. Cần ưu tiên rủi ro

Chuyển dữ liệu để tránh node sắp đầy có tính cấp bách khác với rebalance nhằm cải thiện cân bằng đều từ 60% về 55% disk usage. Migration risk/impact phải được so với **rủi ro nếu không chuyển**.

---

## 16. Điều tiết và QoS: giữ SLO trong quá trình cân bằng

Một chính sách migration không chỉ là “tối đa bao nhiêu MB/s”. Cần kết hợp **tốc độ, độ đồng thời, mức tải foreground và trạng thái storage**.

### 16.1. Các nút điều khiển thường gặp

- Giới hạn bytes/s trên từng node.
- Giới hạn số shard/range migration đồng thời.
- Giới hạn số luồng streaming.
- Cửa sổ chạy ban đêm hoặc off-peak.
- Tạm dừng khi disk free dưới ngưỡng.
- Tạm dừng khi foreground p99 vượt SLO.
- Giảm tốc khi compaction backlog/replication lag tăng.
- Thay đổi batch size hoặc chunk size theo hỗ trợ của engine.
- Ưu tiên migration nguy cấp (node sắp đầy) hơn rebalance thẩm mỹ.

### 16.2. Controller khái niệm

~~~text
Every control interval:
  Observe foreground p99, error rate,
          destination free disk, CPU, IOPS,
          compaction backlog, replica lag.

  If emergency disk risk or correctness risk:
      stop admitting new migrations.

  Else if foreground p99 > SLO or errors increase:
      reduce migration concurrency/bandwidth.

  Else if backlog stable and sufficient headroom:
      increase migration budget gradually.

  Enforce minimum hold period before changing rate.
~~~

Đây là **pseudocode chính sách**, không phải thuật toán điều khiển ổn định có thể dùng nguyên xi. Ngưỡng/công thức phải được thử trong staging và cân nhắc độ trễ feedback để tránh dao động.

### 16.3. Hysteresis

Nếu p99 đang dao động quanh 200 ms, controller tăng/giảm migration mỗi giây có thể gây oscillation. Dùng:

- Ngưỡng tăng khác ngưỡng giảm.
- Cửa sổ quan sát.
- Cooldown.
- Giới hạn tốc độ thay đổi.
- Phân loại sự cố có nguồn gốc từ migration hay từ traffic bình thường.

### 16.4. Budget foreground trước

Một cách đặt policy:

~~~text
Foreground p99 target:    200 ms
Error rate budget:          < 0.2%
Disk free floor:            >= 20%
Network migration cap:     150 MiB/s/node
Concurrent incoming jobs:  1 per destination
~~~

Đây là **con số giả định để thảo luận**, không phải ngưỡng khuyến nghị cố định. SLO, data size và IOPS của hệ thật mới quyết định.

### 16.5. SLO có thể buộc đổi kế hoạch

Nếu node nguồn đã 95% disk usage, throttle quá thấp có thể khiến node hết đĩa trước khi chuyển xong. Khi đó cần một giải pháp an toàn khác:

- Tăng storage trước.
- Bổ sung capacity/điều chỉnh retention theo chính sách.
- Tạm hoãn workload không cấp thiết.
- Chuyển những shard có lợi ích lớn nhất trước.
- Dùng maintenance mode với thông báo rõ nếu cần.

Không nên dùng “không ảnh hưởng người dùng” làm mục tiêu tuyệt đối khi chính hệ đang ở tình trạng nguy cấp; cần cân đối giữa các rủi ro.

---

## 17. Dự toán dung lượng tạm theo lịch chạy đồng thời

Giả sử một node đích nhận ba migration, mỗi migration cần:

~~~text
Shard A: 180 GiB
Shard B: 240 GiB
Shard C: 200 GiB
~~~

Nếu chạy đồng thời, peak temporary usage có thể cao hơn chạy tuần tự. Nhưng **không nhất thiết** bằng tổng các temporary peaks nếu các giai đoạn không trùng nhau; cần mô phỏng lịch.

### 17.1. Mô hình lịch

Gọi \(x_j(t)\) là dung lượng migration j chiếm trên đích ở thời điểm t.

\[
D_{\text{used}}(t)
=
D_{\text{base}}(t)+\sum_j x_j(t)+D_{\text{other-temp}}(t).
\]

Điều kiện an toàn:

\[
\max_t D_{\text{used}}(t)
\le D_{\text{capacity}}-H.
\]

Đây là lý do cần xét **đỉnh theo thời gian**, không chỉ số byte cuối cùng.

### 17.2. Sao chép tuần tự hay song song?

**Tuần tự:**

- Peak network và disk thấp hơn.
- Dễ điều tra lỗi.
- Thời gian hoàn tất toàn batch có thể lâu hơn.

**Song song:**

- Có thể tận dụng nhiều source/destination độc lập.
- Có thể kết thúc nhanh hơn khi tài nguyên còn dư.
- Tăng peak I/O, memory, temporary storage và độ phức tạp điều phối.

### 17.3. Batch theo failure domain

Nếu cùng lúc chuyển nhiều replica của cùng shard hoặc nhiều shard quan trọng trong một zone, khả năng chịu lỗi có thể giảm trong cửa sổ migration.

Một scheduler nên tôn trọng **replica safety constraints** và giới hạn concurrent migrations trên cùng failure domain, không chỉ capacity.

---

## 18. Tính capacity khi thêm node

Giả sử cluster có 6 node, mỗi node đang lưu trung bình 1,2 TiB dữ liệu vật lý. Bỏ qua skew và overhead để minh họa:

\[
D_{\text{physical,total}}
=6\times1.2=7.2\text{ TiB}.
\]

Thêm 2 node, nếu cuối cùng phân bổ đều 8 node:

\[
D_{\text{target,node}}
=\frac{7.2}{8}=0.9\text{ TiB}.
\]

Hai node mới sẽ nhận tổng khoảng:

\[
2\times0.9=1.8\text{ TiB}
\]

**dữ liệu vật lý**, nếu topology và placement cho phép phân phối như vậy và tổng số bản lưu không đổi.

### 18.1. Không nhân RF lần nữa

Nếu số 7,2 TiB đã là **physical stored bytes trên toàn cluster**, nó đã bao gồm replica theo cách đo. Nhân tiếp RF=3 sẽ đếm trùng.

Nếu số đầu vào là **logical unique bytes**, phải tính số replica và overhead khi lập ngân sách physical storage.

### 18.2. Source read và destination write

Để chuyển 1,8 TiB physical stored bytes:

- Ít nhất khoảng 1,8 TiB cần xuất hiện ở đích.
- Nguồn có thể phải đọc một lượng tương ứng hoặc khác do protocol/index/checksum.
- Network có thể mang lượng tương ứng, lớn hơn hoặc nhỏ hơn tùy compression, copy source, retries và delta.
- Node cũ có thể chưa giải phóng tương ứng ngay.

### 18.3. Thời gian phụ thuộc placement

Nếu tổng incoming là 1,8 TiB nhưng cả hai node đích cùng chia một network uplink 200 MiB/s, cận dưới khác hẳn trường hợp mỗi node có 200 MiB/s độc lập.

Dự toán phải xác định **nút thắt chung** chứ không chỉ chia dữ liệu cho số node mới.

### 18.4. Thay đổi RF làm bài toán khác

Nếu vừa thêm node vừa tăng RF từ 2 lên 3, tổng physical stored bytes có thể tăng đáng kể, không thể dùng mô hình “chỉ dàn đều dữ liệu hiện có”. Cần tách **new replica creation** khỏi **relocation existing replicas**.

---

## 19. Một worksheet dự toán rebalancing

Một kế hoạch có thể dùng bảng:

| Tham số | Ký hiệu | Ví dụ | Nguồn đo |
|---|---|---:|---|
| Physical bytes cần copy | \(B\) | 600 GiB | Engine/shard metrics |
| Effective throttle | \(v_t\) | 150 MiB/s | Config/benchmark |
| Source read sustainable | \(v_s\) | 250 MiB/s | Storage telemetry |
| Destination write sustainable | \(v_d\) | 210 MiB/s | Storage telemetry |
| Network sustainable | \(v_n\) | 190 MiB/s | Network telemetry |
| Change generation rate | \(r\) | 50 MiB/s | WAL/CDC metrics |
| Catch-up processing | \(c\) | 130 MiB/s | Staging test |
| Peak temp headroom | \(H_t\) | 160 GiB | Engine/filesystem |
| Concurrent jobs | \(J\) | 2 | Scheduler |
| Foreground p99 target | \(L\) | 200 ms | Product SLO |
| Source/dest AZ | — | AZ-A → AZ-B | Placement |
| Cross-AZ billable bytes | — | Phải đo | Cloud cost data |

### 19.1. Thời gian copy thấp nhất

Với bốn giới hạn:

\[
v_{\text{effective}}
\le \min(150,250,210,190)=150\text{ MiB/s}.
\]

\[
T_{\text{copy,min}}
\ge\frac{600\times1024}{150}
=4096\text{ s}.
\]

Chưa có thể cam kết thời gian kết thúc vì catch-up, disk/CPU contention, retry và cutover chưa được tính.

### 19.2. Catch-up

Nếu backlog sau copy là 45 GiB:

\[
D=45\times1024=46080\text{ MiB},
\]

\[
T_{\text{catchup}}
\approx\frac{46080}{130-50}
=576\text{ s}\approx9.6\text{ phút}.
\]

Như vậy thời gian lý tưởng cho hai pha đã khoảng **77,9 phút**, chưa có verify/cutover/cleanup và biến động tốc độ. Đây chỉ là ví dụ mô hình.

### 19.3. Tổng ngân sách

Phải giữ ba con số riêng:

1. **Network bytes**: bản copy + delta + retry + overhead.
2. **Disk temporary peak**: trạng thái chồng lấn ở nguồn và đích.
3. **Calendar time / SLO risk**: thời gian thực hệ bị tác vụ nền chiếm tài nguyên.

Không suy một con số từ hai con số còn lại bằng một hệ số chung.

---

## 20. Ví dụ Java: công cụ ước lượng cận dưới

Đây là chương trong lộ trình Java, nên có thể đóng gói công thức đơn giản thành một hàm để lập kế hoạch.

~~~java
public final class RebalanceEstimate {

    private RebalanceEstimate() {
    }

    public record Inputs(
        double gibToCopy,
        double sourceReadMibPerSec,
        double networkMibPerSec,
        double destinationWriteMibPerSec,
        double migrationCapMibPerSec
    ) {
    }

    public static double effectiveMibPerSec(Inputs in) {
        if (in.gibToCopy() < 0
                || in.sourceReadMibPerSec() <= 0
                || in.networkMibPerSec() <= 0
                || in.destinationWriteMibPerSec() <= 0
                || in.migrationCapMibPerSec() <= 0) {
            throw new IllegalArgumentException("Invalid estimate inputs");
        }

        return Math.min(
            Math.min(
                in.sourceReadMibPerSec(),
                in.networkMibPerSec()
            ),
            Math.min(
                in.destinationWriteMibPerSec(),
                in.migrationCapMibPerSec()
            )
        );
    }

    public static double copyLowerBoundSeconds(Inputs in) {
        double mib = in.gibToCopy() * 1024.0;
        return mib / effectiveMibPerSec(in);
    }

    public static double catchupSeconds(
        double pendingMib,
        double catchupMibPerSec,
        double newChangesMibPerSec
    ) {
        if (pendingMib < 0
                || catchupMibPerSec <= newChangesMibPerSec
                || newChangesMibPerSec < 0) {
            throw new IllegalArgumentException(
                "Catch-up cannot converge under supplied rates"
            );
        }
        return pendingMib /
            (catchupMibPerSec - newChangesMibPerSec);
    }

    public static void main(String[] args) {
        Inputs in = new Inputs(
            600.0, 250.0, 190.0, 210.0, 150.0
        );

        double copySeconds = copyLowerBoundSeconds(in);
        double catchupSeconds = catchupSeconds(
            45.0 * 1024.0, 130.0, 50.0
        );

        System.out.printf(
            "Copy lower bound: %.1f minutes%n",
            copySeconds / 60.0
        );

        System.out.printf(
            "Catch-up estimate: %.1f minutes%n",
            catchupSeconds / 60.0
        );
    }
}
~~~

### 20.1. Giới hạn của công cụ

- Dùng `double` để minh họa lập kế hoạch, không phải tính tiền với yêu cầu decimal chính xác.
- Giả định tốc độ không đổi.
- Không tự tính retry/compaction/cache/metadata.
- `copyLowerBoundSeconds` không phải dự đoán p95/p99 hoặc ETA production.
- Không xử lý lịch nhiều job dùng chung disk/NIC.
- Không thay thế metric/benchmark của DBMS.

### 20.2. Tránh đặt tên sai

Không nên đặt hàm `guaranteedFinishSeconds()` vì mô hình không cho một cam kết thời gian. Tên `copyLowerBoundSeconds()` đúng hơn: cho biết **tối thiểu trong giả định**.

---

## 21. MongoDB: cân bằng chunk/range và ảnh hưởng tới workload

Trong MongoDB sharded cluster, dữ liệu được phân phối theo shard key và các range/chunk; cơ chế balancer và migration có thể di chuyển range để đáp ứng placement.

### 21.1. Những thứ cần quan sát

- Số chunk/range hoặc dung lượng cần di chuyển.
- Mức độ lệch dữ liệu/tải giữa shard.
- Node nguồn/đích và disk headroom.
- Tốc độ migration và thời gian catch-up.
- Query routing trong lúc placement thay đổi.
- Index/working set và cache.
- Write/read latency trên các shard liên quan.
- Balancer activity và lỗi migration.

MongoDB có những cơ chế và tùy chọn vận hành **thay đổi theo phiên bản**; không mặc định tên tham số hay thuật toán migration của một bản cũ vẫn đúng với bản hiện hành.

### 21.2. Dữ liệu logic và byte truyền

Một range gồm 100 GiB logical documents không có nghĩa đúng 100 GiB truyền. Storage compression, index, oplog catch-up, verification, retries và cách engine copy range ảnh hưởng traffic thực.

### 21.3. Chuyển range nóng

Nếu range có traffic cao, copy ban đầu có thể hoàn tất nhưng catch-up tiếp tục lớn. Đích cũng chưa có cache nóng như nguồn.

**Rebalance không tự giảm QPS của hot key** nếu key vẫn thuộc một range có một chủ sở hữu. Muốn chia tải có thể cần shard-key/bucketing changes theo workload.

### 21.4. Truy vấn khi migration

Router có metadata placement và phải tương tác với các protocol của hệ khi range chuyển owner. Không tự viết direct-to-shard router mà bỏ qua metadata epoch/migration handling của MongoDB.

### 21.5. Plan an toàn

Dùng công cụ giám sát và tài liệu phiên bản thực tế để xác định tốc độ/giới hạn migration. Thực hiện canary với range nhỏ, theo dõi p99, disk, network và lỗi trước khi mở rộng.

---

## 22. Cassandra: bootstrap, streaming, repair và compaction

Cassandra phân phối partition theo token và replication strategy; khi thêm hoặc rút node, việc bootstrap/decommission có thể stream ranges/SSTables.

### 22.1. Bootstrap node mới

Một node mới có thể cần nhận dữ liệu từ các replica hiện có để đảm nhận những token ranges được phân bổ. Từ góc nhìn capacity:

~~~text
Node nguồn:
  disk read + stream out

Node mới:
  stream in + disk write

Cluster:
  placement/ownership update + replication safety
~~~

### 22.2. Vnodes và số range

Virtual nodes giúp chia ownership thành nhiều token ranges, nhưng cũng có nghĩa một node có thể liên quan nhiều ranges và nguồn streaming khác nhau. Số vnodes/token topology ảnh hưởng scheduling và chi phí quản lý.

Không suy “thêm một node” đồng nghĩa chỉ có một dòng copy từ một source.

### 22.3. Compaction

Cassandra dùng SSTables và compaction strategies. Sau streaming/flush, compaction có thể tiếp tục dùng disk/CPU và cần headroom.

Ngoài số byte stream, cần theo dõi:

- Pending compactions.
- Disk read/write utilization.
- Memtable flush/backpressure.
- Commit log pressure.
- Partition size distribution.
- Read/write p99.
- Streaming sessions và failures.

### 22.4. Repair khác bootstrap

Repair/anti-entropy kiểm tra và khôi phục sự hội tụ giữa replica; nó có thể tạo thêm disk/network load và không đồng nhất với quá trình bootstrap. Cân lịch repair và migration dựa trên chính sách của cluster, không tự tắt repair vô thời hạn.

### 22.5. Locality và cross-DC

Replication factor theo từng datacenter và consistency level ảnh hưởng placement và traffic. Nếu streaming đi qua link cross-DC, chi phí/RTT có thể khác hẳn transfer trong DC.

### 22.6. Hot partition

Cassandra partition key quyết định routing. Nếu một partition cực lớn/hot, rebalance token ownership có thể chuyển hotspot sang node khác mà không chia nhỏ partition. Cần xem lại data model/bucketing nếu workload yêu cầu.

---

## 23. Elasticsearch/OpenSearch: shard relocation và cache lạnh

Elasticsearch/OpenSearch lưu dữ liệu trong primary/replica shards. Rebalance hoặc relocation có thể di chuyển shard copy giữa các node.

### 23.1. Những công việc phát sinh

- Copy các index segments/file liên quan.
- Recovery và replay thao tác mới theo protocol.
- Kiểm tra shard đã đủ điều kiện.
- Cập nhật shard allocation/routing.
- Khởi tạo query cache/page cache ở node mới.
- Có thể tiếp tục segment merge sau khi di chuyển.

### 23.2. Recovery throttle và concurrency

Các hệ search thường có cơ chế giới hạn tốc độ/concurrency recovery hoặc số shard di chuyển đồng thời, nhưng tên setting và semantics cần xem tài liệu phiên bản đang chạy.

Đặt quá thấp: quá trình rebalance chậm.

Đặt quá cao: search/indexing latency tăng, disk/network saturation và node đích bị quá tải.

### 23.3. Search fan-out tăng rủi ro tail latency

Một search cần kết quả từ nhiều shard groups; nếu một shard đang recover và phản hồi chậm, global search có thể chậm theo, tùy query execution và timeout policy.

### 23.4. Cache warm-up

Một shard mới nhận có thể chứa đầy đủ index trên disk nhưng chưa có cache như shard cũ. Sau relocation, p99 có thể giảm dần khi workload làm nóng page cache/query cache. Đừng chỉ đánh giá ngay tại “relocation finished”.

### 23.5. Nhiều shard nhỏ cũng có giá

Nếu index có rất nhiều shard quá nhỏ, quản lý metadata, recovery concurrency và heap overhead có thể cao. Ngược lại, shard quá lớn có recovery time lâu và hotspot. Chọn shard size/count cần dựa vào workload, retention và recovery objectives, không phải một con số toàn ngành.

---

## 24. Redis Cluster: di chuyển slot và các key

Redis Cluster phân phối key trên các hash slots. Resharding có thể chuyển ownership của slot và những key thuộc slot từ node này sang node khác.

### 24.1. Routing trong lúc slot chuyển

Client hỗ trợ Redis Cluster xử lý redirect theo protocol như `MOVED` hoặc `ASK` khi placement thay đổi.

Không hard-code mapping hostname theo slot rồi giữ mãi trong ứng dụng.

### 24.2. Key lớn

Một key rất lớn hoặc cấu trúc dữ liệu lớn có thể khiến việc chuyển một key tốn thời gian, CPU, network và memory đáng kể.

“Chỉ chuyển một slot” không có nghĩa số byte ít, vì phân bố key/value có thể lệch.

### 24.3. Hash tag và hotspot

Các key chia sẻ cùng hash tag có thể được colocate vào một slot để phục vụ multi-key operations. Đây là lợi ích về locality nhưng có thể khiến slot cực nóng và khó phân tán workload hơn.

### 24.4. Persistence và failover

Redis primary/replica và persistence (RDB/AOF) có semantics riêng. Move/reshard thành công không tự chứng minh mọi write đã durable sau node crash.

Cần hiểu trạng thái key transfer, client retry và hạn chế multi-key atomic operations theo Redis Cluster.

### 24.5. Không gộp lệnh tự quản với managed service

Nếu Redis được cung cấp qua một dịch vụ managed, khả năng cấu hình/balancer API có thể khác tự vận hành. Kiểm tra giới hạn và công cụ của đúng môi trường.

---

## 25. DynamoDB và dịch vụ managed: không phải lúc nào tự chuyển partition được

DynamoDB quản lý việc chia physical partitions và phân phối storage/capacity ở tầng dịch vụ. Ứng dụng không có một API phổ quát “di chuyển shard X từ node A sang node B” giống hệ tự quản.

### 25.1. Vẫn phải quan tâm điểm nóng

Thiết kế partition key không đều có thể tạo tập trung traffic. Những chỉ số quan trọng:

- Throttled requests.
- Partition-key distribution hoặc contributor insights nếu khả dụng.
- Read/write capacity consumption.
- Latency.
- Hot key/range.
- GSI write/query workload.

### 25.2. Đánh đổi ở tầng mô hình dữ liệu

Nếu một partition key có quá nhiều traffic, ứng dụng có thể cần:

- Write sharding bằng synthetic suffix.
- Time bucket.
- Cache.
- Separate access pattern/index.
- Pre-aggregation.
- Idempotent read/merge across buckets.

Những thay đổi này có **chi phí backfill, lưu tạm, index write amplification và dual-read/dual-write** ngay cả khi engine tự quản physical partitions.

### 25.3. Managed không có nghĩa không tốn tiền hoặc không có lag

Thêm index, export dữ liệu, rebuild read model, migrate bảng hay đổi schema khóa vẫn có thể tạo:

- Read/write capacity consumption.
- Storage tăng tạm.
- CDC/stream traffic.
- Object storage cost.
- Backfill duration.
- Eventual consistency lag.

Nhưng không nên giả định người dùng nhìn thấy hay điều khiển chính xác mọi internal shard movement của dịch vụ.

### 25.4. Khi định giá

Sử dụng pricing, quota, capacity mode và tính năng được công bố **cho dịch vụ và region cụ thể**, tránh suy ra trực tiếp từ chi phí một máy NoSQL tự quản.

---

## 26. Cân bằng và secondary index/read model

Một schema NoSQL có thể dùng nhiều read models cho nhiều access patterns:

~~~text
Order source collection
  -> GSI / materialized view
  -> Search index
  -> Analytics pipeline
  -> Cache
~~~

### 26.1. Backfill làm tải nguồn tăng

Tạo lại index hoặc read model có thể cần quét một lượng lớn dữ liệu nguồn. Nếu làm cùng rebalance, source phải chịu cả streaming **và** backfill scan.

### 26.2. Change stream lag

Trong lúc backfill, source vẫn thay đổi. Read model cần xử lý event từ một checkpoint, loại trùng, bảo toàn thứ tự trong phạm vi nghiệp vụ và theo kịp dữ liệu.

### 26.3. Dung lượng tạm ở hệ đích

Search/analytics có thể giữ cả index cũ và mới trong giai đoạn rebuild hoặc blue/green. Chi phí lưu tạm có thể nằm **ngoài database nguồn**.

### 26.4. Cân bằng nguồn không tự cân bằng read model

Một source DB được reshard tốt không có nghĩa GSI/search shards cũng cân bằng. Mỗi hệ có placement và hotspot riêng.

### 26.5. Kiểm tra freshness

Không nên dùng thời điểm “rebalance completed” để tuyên bố search/index đã mới. Theo dõi watermark/lag của từng read model.

---

## 27. Các rủi ro vận hành và cách phản ứng

| Sự cố | Dấu hiệu | Rủi ro | Hướng phản ứng |
|---|---|---|---|
| Network saturation | Egress cao, retransmit, p99 tăng | Foreground timeout | Giảm concurrency/rate, xem topology |
| Destination disk thấp | Free space giảm nhanh | Disk full, write failure | Pause admission, tăng space, xem temp |
| Source disk read quá tải | Read latency/queue tăng | API read chậm | Throttle streaming, tránh scan khác |
| Compaction backlog | Pending compactions cao | Read/write amplification | Điều tiết migration, capacity planning |
| CDC/replica lag tăng | Lag vượt SLO | Read model stale, catch-up chậm | Giảm nguồn tải, tăng catch-up capacity |
| Cutover không hội tụ | Delta backlog không giảm | Không thể chuyển owner an toàn | Kiểm tra c>r, protocol, throttle |
| Cache hit rate giảm | Miss tăng sau relocation | p99 cao sau cutover | Gradual warm-up/traffic |
| Hot shard đổi chỗ | QPS nóng ở đích | Không giải quyết hotspot | Revisit partition model |
| Retry storm | Request/stream retries tăng | Amplified load | Backoff/jitter, budget, fix root cause |
| Routing metadata stale | Redirect/errors tăng | Đọc/ghi sai owner nếu protocol yếu | Refresh router metadata |
| Backup trễ | Backup age tăng | RPO vượt mục tiêu | Replan task background, bảo vệ backup |
| Repair tắc nghẽn | Anti-entropy backlog | Replica divergence | Lập lịch và hạn mức đủ |
| One-zone overplacement | Replica cùng zone | Giảm khả năng chịu lỗi | Kiểm tra placement/failure domains |
| Cost spike | Network/storage bills tăng | Vượt ngân sách | Cập nhật traffic estimates, schedule |

### 27.1. Ưu tiên bảo toàn dữ liệu

Khi nghi ngờ hai owner cùng nhận authoritative writes hoặc catch-up sai thứ tự, không nên chỉ tăng tốc transfer để “cho xong”. Cần giữ protocol an toàn, dùng công cụ vận hành chính thức và tạm dừng migration nếu cần.

### 27.2. Lỗi disk full thường có phản ứng dây chuyền

Disk full có thể làm journal/compaction/replication lỗi và tăng rủi ro recovery. Vì vậy **disk headroom là điều kiện trước khi bắt đầu**, không phải metric chỉ xem sau khi transfer xong.

### 27.3. Không làm hỏng production để thử

Fault injection phá mạng, kill process hoặc làm đầy disk chỉ nên thực hiện ở staging/test được cấp quyền, hoặc trong quy trình production game day được phê duyệt với rollback rõ.

---

## 28. Monitoring: dashboard nào cần có?

Một dashboard phục vụ rebalancing nên có cả **mốc tiến độ** và **ảnh hưởng tới foreground**.

| Nhóm | Metric | Câu hỏi |
|---|---|---|
| Tiến độ | Bytes moved, remaining, per-job state | Đã chuyển bao nhiêu? |
| Hiệu suất | Effective MiB/s, retry rate | Có bị nghẽn hay gửi lại? |
| Network | In/out by node, cross-zone bytes | Link nào bị bão hòa? |
| Storage | Used/free/temp bytes, disk read/write | Có đủ headroom? |
| I/O latency | fsync p99, read/write queue | Foreground có bị tranh I/O? |
| Background | Compaction, repair, backup backlog | Có việc nào bị dồn? |
| Catch-up | Lag bytes/time, applied sequence | Đích có theo kịp nguồn? |
| CPU | User/system CPU, throttling | Compression/checksum quá nặng? |
| Memory | Cache hit/miss, GC, buffer usage | Cache có bị đẩy ra? |
| Foreground | Read/write p95/p99, timeout, 5xx | Người dùng có bị ảnh hưởng? |
| Routing | Redirect, stale metadata, owner epoch | Cutover an toàn? |
| Placement | Bytes/QPS per shard, replica by zone | Có cân bằng thực? |
| Completeness | Validation errors, mismatch count | Có sai/mất dữ liệu? |
| Cost | Cross-zone egress, snapshot/temp storage | Ngân sách phát sinh? |
| Recovery | Backup age, restore checkpoints | Khả năng phục hồi còn tốt? |

### 28.1. Không chỉ nhìn percent complete

Nếu dashboard hiển thị:

~~~text
Copy phase: 100%
Catch-up lag: 95 GiB
Temporary disk free: 5%
Compaction backlog: tăng
~~~

thì migration **chưa an toàn để coi là hoàn thành** chỉ từ phần trăm copy.

### 28.2. Lấy số theo source và destination

Một average CPU 50% toàn cluster có thể che việc node đích đạt 100% disk utilization.

Phải drill down theo:

- Node.
- Shard/range.
- Tenant nếu khả thi.
- AZ/region.
- Workload class.
- Thời điểm trước/trong/sau migration.

### 28.3. Quan sát hiệu quả sau chuyển

Kết quả thành công không chỉ là “không còn bytes pending”. Hãy so:

- Skew dung lượng trước/sau.
- Skew QPS/IOPS trước/sau.
- p99 API trước/sau.
- Disk headroom.
- Repair/compaction backlog.
- Cache warm-up.
- Lượng transfer và thời gian thực.
- Chi phí phát sinh.

---

## 29. Runbook cân bằng từng bước

### Bước 1 — Xác định động cơ

- Node sắp đầy?
- Thêm node?
- Hotspot QPS?
- Cần thay placement/failure domain?
- Decommission?
- Đổi shard key vì access pattern?

**Không dùng một thao tác di chuyển dữ liệu để chữa mọi loại hotspot.**

### Bước 2 — Chốt phạm vi

Ghi:

~~~text
Source:
Destination:
Logical shards/ranges:
Replica copies actually moving:
Physical bytes expected:
Foreground QPS and write rate:
Cross-AZ/region boundaries:
Migration window:
Owner/route cutover protocol:
Rollback/repair approach:
~~~

### Bước 3 — Ước lượng headroom

Đánh giá disk, CPU, memory, network, IOPS, log retention, replica count và failure domains ở cả source/destination.

### Bước 4 — Đặt safety guardrails

Ví dụ:

~~~yaml
migrationPolicy:
  maxConcurrentIncomingPerNode: 1
  migrationNetworkCapMiBps: 100
  pauseOnForegroundP99Ms: 250
  pauseOnDiskFreeBelowPercent: 20
  stopOnReplicaSafetyViolation: true
  requireRoutingMetadataHealthy: true
~~~

Đây là **mẫu policy nội bộ minh họa**, không phải file cấu hình được các NoSQL DBMS tự nhận. Các ngưỡng cần lựa chọn từ dữ liệu SLO thực tế.

### Bước 5 — Chạy canary

Di chuyển một shard/range nhỏ, theo dõi:

- Tốc độ thực vs dự toán.
- Disk temp peak.
- Source/destination IOPS.
- Foreground p99.
- Catch-up.
- Cleanup.
- Khả năng khôi phục khi gặp lỗi.

### Bước 6 — Mở rộng từng đợt

Tăng concurrency khi metric cho phép, không tăng chỉ vì job đầu không báo lỗi. Phân bổ job tránh nhiều replica critical cùng di chuyển.

### Bước 7 — Xác nhận cutover

Dùng trạng thái/điểm kiểm chứng của DBMS: ownership, epoch, catch-up, successful migration result, query correctness. Không tự xóa bản nguồn.

### Bước 8 — Theo dõi hậu chuyển

Quan sát đủ một chu kỳ workload hoặc giai đoạn cache warm-up/compaction phù hợp, không dừng monitoring ngay khi control plane báo thành công.

### Bước 9 — Dọn dẹp theo protocol

Để engine dọn bản cũ/tạm; kiểm tra backup và repair còn đúng lịch. Tránh can thiệp thủ công vào file storage nội bộ.

### Bước 10 — Ghi lại thực tế

So sánh:

~~~text
Estimated bytes vs actual bytes
Estimated hours vs actual hours
Peak temp disk vs plan
User p99 impact
Failures/retries
Cost vs budget
Balance improvement
~~~

Thông tin ấy giúp lần kế hoạch sau chính xác hơn.

---

## 30. Bài tập 1: tính thời gian di chuyển có đơn vị

Một migration cần chuyển **480 GiB** dữ liệu vật lý. Tốc độ đo được:

~~~text
Source read:      300 MiB/s
Network usable:   180 MiB/s
Destination write:220 MiB/s
Migration cap:    120 MiB/s
~~~

Hãy trả lời:

1. Bottleneck theo mô hình đơn giản là gì?
2. Cận dưới copy là bao lâu?
3. Nếu network cap tăng lên 200 MiB/s nhưng dest vẫn 220 MiB/s, tốc độ nào thành bottleneck?
4. Nếu chạy hai job cùng destination, có thể cộng tốc độ mỗi job không?
5. Chưa tính những thành phần chi phí nào?

### Gợi ý lời giải

Ban đầu:

\[
v=\min(300,180,220,120)=120\text{ MiB/s}.
\]

\[
T_{\min}=\frac{480\times1024}{120}
=4096\text{ s}\approx68.3\text{ phút}.
\]

Nếu chỉ tăng `migration cap` lên 200 MiB/s, network usable 180 MiB/s trở thành bottleneck; không tự đạt 200. Hai job dùng chung đích phải chia tài nguyên.

---

## 31. Bài tập 2: disk headroom

Một node có volume **2 TiB**:

~~~text
Đang dùng:                  1.20 TiB
Incoming replica:            420 GiB
Temp files:                  110 GiB
Compaction reserve:          170 GiB
Foreground growth:            40 GiB
Safety reserve policy:       160 GiB
~~~

Yêu cầu:

1. Quy đổi 1.20 TiB sang GiB.
2. Cộng peak usage theo giả định tất cả khoản phát sinh đồng thời.
3. Còn bao nhiêu GiB so với 2 TiB?
4. Nếu kết quả vượt capacity, có thể giảm concurrency hoặc tăng disk theo cách nào?
5. Vì sao delete bản cũ ở source chưa chắc giải phóng dung lượng ngay?

Gợi ý:

\[
1.20\text{ TiB}=1228.8\text{ GiB}.
\]

\[
D_{\text{plan}}=1228.8+420+110+170+40+160
=2128.8\text{ GiB}.
\]

Dung lượng 2 TiB = 2048 GiB, nên kế hoạch **thiếu khoảng 80,8 GiB** theo mô hình này. Không nên bắt đầu với các giả định ấy.

---

## 32. Bài tập 3: write delta và catch-up

Giả định:

~~~text
Copy hoàn tất, còn backlog 120 GiB delta.
Nguồn sinh thay đổi mới: 80 MiB/s.
Đích có thể replay: 160 MiB/s.
~~~

1. Tốc độ backlog giảm là bao nhiêu?
2. Thời gian lý tưởng để bắt kịp?
3. Nếu nguồn tăng lên 180 MiB/s mà đích vẫn 160 MiB/s thì sao?
4. Nếu log retention không đủ, nguy cơ gì?
5. Cần metric và guardrail nào?

### Gợi ý

\[
T\approx\frac{120\times1024}{160-80}
=1536\text{ s}\approx25.6\text{ phút}.
\]

Khi tốc độ sinh thay đổi 180 MiB/s lớn hơn replay 160 MiB/s, backlog **tăng**, không tự hội tụ trong mô hình tốc độ không đổi.

---

## 33. Bài tập 4: chi phí cross-zone

Một lần rebalance chuyển:

~~~text
Initial copy:      900 GiB
Catch-up delta:    140 GiB
Retries:            60 GiB
Metadata/network:   10 GiB
~~~

Giả sử toàn bộ 4 dòng có phí theo một đơn giá **giả định** 0,015 USD/GiB.

1. Tổng billable traffic theo giả định?
2. Tiền truyền dữ liệu?
3. Nếu 30% bytes truyền nằm trong cùng zone và không bị tính phí theo hợp đồng thực tế, phải chỉnh công thức thế nào?
4. Những loại cost nào khác network còn phát sinh?
5. Vì sao không nên dùng đơn giá giả định để lập hóa đơn cloud?

### Gợi ý

\[
B=900+140+60+10=1110\text{ GiB}.
\]

\[
C=1110\times0.015=16.65\text{ USD}.
\]

Trong thực tế phải phân traffic theo đúng bảng giá và topology đã xác minh.

---

## 34. Bài tập 5: data skew và workload skew

Một cluster có bốn shard:

| Shard | Stored data | Foreground QPS | CPU |
|---|---:|---:|---:|
| A | 500 GiB | 1.000 | 25% |
| B | 500 GiB | 1.200 | 28% |
| C | 500 GiB | 1.100 | 27% |
| D | 500 GiB | 40.000 | 93% |

Câu hỏi:

1. Cluster có mất cân bằng dung lượng không?
2. Cluster có mất cân bằng workload không?
3. Chuyển nguyên shard D sang node khác có giảm QPS của shard D không?
4. Nếu 90% QPS của D tập trung vào một key, thêm node giúp được gì?
5. Có thể dùng cache, bucket, rate limit hoặc redesign access pattern thế nào?
6. Những thay đổi đó ảnh hưởng consistency/aggregation ra sao?

**Gợi ý:** cân bằng bytes không đồng nghĩa cân bằng resource usage. Hot key cần giải quyết ở data model/workload, không chỉ vị trí.

---

## 35. Bài tập 6: lập kế hoạch bootstrap node

Một cluster Cassandra có:

~~~text
6 nodes hiện tại
RF=3
Mỗi node dùng trung bình 900 GiB physical data
Thêm 3 nodes
Tải write tăng 15% trong migration
Compaction đang chiếm 25% disk throughput
Hai node mới ở một availability zone khác
~~~

Hãy lập bảng:

- Total stored physical bytes hiện tại.
- Average target per node nếu dữ liệu phân bổ đều và RF không đổi.
- Incoming physical bytes tối thiểu vào ba node mới theo giả định.
- Những nguồn streaming có thể tham gia.
- Network/AZ charges phải kiểm tra.
- Tốc độ có thể cấp migration khi compaction vẫn chạy.
- Disk temp headroom từng node.
- Repair/backup cần giữ thế nào.
- Rủi ro khi nhiều node cùng bootstrap.
- Những metric và điều kiện dừng.

Không được suy từ RF=3 rằng số byte cần chuyển **bắt buộc bằng ba lần tổng dữ liệu vật lý hiện có**.

---

## 36. Bài tập 7: thiết kế policy tự điều tiết bằng Java

Tạo class:

~~~java
public record RebalanceTelemetry(
    double foregroundP99Millis,
    double errorRatePercent,
    double destinationDiskFreePercent,
    double sourceDiskReadLatencyMillis,
    double replicaLagSeconds,
    double compactionBacklogGiB
) {}

public enum MigrationAction {
    INCREASE_BUDGET,
    HOLD_BUDGET,
    DECREASE_BUDGET,
    PAUSE_ADMISSION
}
~~~

Đề xuất quy tắc:

- `PAUSE_ADMISSION` khi disk safety floor bị vượt hoặc có bất thường correctness.
- `DECREASE_BUDGET` khi foreground latency/error tăng.
- `HOLD_BUDGET` khi không đủ thời gian quan sát hoặc metric thiếu.
- `INCREASE_BUDGET` chỉ khi headroom đủ và ổn định qua nhiều chu kỳ.
- Có cooldown/hysteresis và giới hạn min/max.
- Chỉ thay đổi cấu hình bằng công cụ chính thức của DBMS.

Giải thích vì sao một controller không có hysteresis có thể dao động khi p99 tăng/giảm quanh ngưỡng.

---

## 37. Bài tập 8: cutover có lỗi

Giả sử:

~~~text
Epoch 17: node A là authoritative owner.
Node D copy xong snapshot K.
D bắt kịp changelog tới K+100.
Routing metadata chuyển sang epoch 18.
Node A bị pause, sau đó tỉnh lại.
Một client cũ vẫn gửi write tới A.
~~~

Hãy trả lời:

1. Node A có được tự ý xác nhận write ở epoch 17 không?
2. Routing metadata stale được phát hiện bằng cách nào?
3. Fencing/epoch giúp gì?
4. Nếu D chưa áp dụng một write đã ACK ở A, nguy cơ gì?
5. Vì sao rollback về A không tự an toàn sau D nhận thêm writes?
6. Cần những log/metrics/checkpoints nào để điều tra?
7. Nếu migration đã báo completed nhưng cache ở D lạnh, đánh giá hiệu năng thế nào?

---

## 38. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Thêm node xong là tải tự giảm ngay.” | Bootstrap/copy/catch-up có thể tăng tải tạm thời. |
| “Data move 1 TiB nghĩa network đúng 1 TiB.” | Delta, retry, compression và replication làm khác. |
| “RF=3 nghĩa phải truyền gấp ba mọi lần.” | Phải đếm các replica mới thực sự được tạo/chuyển. |
| “Đã có 10 Gbps thì copy đạt 1,25 GB/s.” | Throughput hữu dụng bị giới hạn bởi I/O/CPU/throttle. |
| “Copy 100% là migration hoàn thành.” | Còn catch-up, verify, cutover, cleanup. |
| “Node nguồn không cần free disk.” | WAL, snapshot, compaction và bản cũ còn chiếm chỗ. |
| “Đích còn đủ chỗ cho dữ liệu cuối là an toàn.” | Temporary/compaction peak có thể làm đầy. |
| “Disk used giảm ngay khi xóa logical data.” | Segment/snapshot/compaction có thể giữ byte. |
| “Compaction không liên quan rebalance.” | Compaction tranh I/O và có thể phát sinh thêm sau stream. |
| “Tăng concurrency luôn nhanh hơn.” | Có thể gặp shared bottleneck và làm p99 xấu đi. |
| “CPU thấp nghĩa migration an toàn.” | Disk/IOPS/network/GC có thể là bottleneck. |
| “Cân bằng byte cũng cân bằng QPS.” | Hot key/range làm workload skew. |
| “Chuyển hot key sang node khác là hết nóng.” | Chỉ đổi vị trí hotspot nếu không đổi mô hình tải. |
| “Tắt hết task nền để đẩy migration.” | Repair/backup/compaction backlog có thể gây rủi ro. |
| “Dual-write là transaction.” | Có thể một bên ghi thành công và một bên thất bại. |
| “Metadata cutover chỉ là đổi hostname.” | Cần ownership epoch, safety và stale-router handling. |
| “Thành công cutover nghĩa cache đã nóng.” | Cold cache làm p99 xấu sau migration. |
| “Managed service thì không có cost rebalancing.” | Backfill, GSI, streams và app-side reshard vẫn tốn. |
| “Một giá cross-AZ dùng cho mọi cloud.” | Giá phụ thuộc provider, region, service, chiều truyền. |
| “Retry stream không có thêm traffic.” | Một phần dữ liệu có thể phải gửi lại. |
| “Một node lỗi chỉ ảnh hưởng job đó.” | Có thể tạo retry storm và ảnh hưởng foreground. |
| “Khi mạng tốt, không cần đo source disk.” | Disk read có thể là bottleneck. |
| “Một job đã chạy được thì tất cả job chạy cùng đều an toàn.” | Peak temporary/concurrency và failure domains khác. |
| “Rebalance xong thì backup và read model cũng theo kịp.” | Mỗi hệ có backlog/freshness riêng. |

---

## 39. Checklist vận hành cuối cùng

Trước khi cân bằng một cluster NoSQL, hãy điền đầy đủ:

- [ ] **Mục tiêu:** giảm disk skew, hot QPS, đổi placement hay decommission?
- [ ] **Phạm vi:** shard/range/replica nào thực sự cần di chuyển?
- [ ] **Bytes:** logical, physical/compressed, index, delta và retry được tính riêng?
- [ ] **Network:** source/destination link, cross-AZ/region và băng thông hữu dụng?
- [ ] **Storage:** disk headroom ở cả nguồn và đích, bao gồm temporary/compaction?
- [ ] **CPU/Memory:** compression, checksum, cache eviction, JVM GC?
- [ ] **Replication:** RF, replica placement và failure domains an toàn?
- [ ] **Background:** repair, compaction, backup, CDC, index build đang chạy?
- [ ] **Catch-up:** tốc độ delta, backlog, log retention, điều kiện hội tụ?
- [ ] **Cutover:** ownership protocol, epoch/lease, stale router, validation?
- [ ] **Performance:** p95/p99 foreground và retry/error budget?
- [ ] **Throttle:** bytes/s, concurrency, admission control, maintenance window?
- [ ] **Rollback/recovery:** trạng thái sau cutover và kế hoạch quay lại?
- [ ] **Cost:** network billable bytes, temp storage, compute và opportunity cost?
- [ ] **Observability:** actual bytes/s, disk/IOPS, lag, progress, balancing skew?
- [ ] **Post-check:** cleanup, cache warm-up, compaction backlog, SLO sau chuyển?
- [ ] **Tài liệu:** số ước tính, số thực đo và bài học cho lần sau?

Checklist này giúp quản lý rủi ro nhưng **không thay thế quy trình cụ thể của DBMS và phiên bản đang sử dụng**.

---

## 40. Tổng kết

Trong NoSQL phân tán, **cân bằng không phải chỉ là bài toán chia đều byte trên những node còn trống**. Nó là một thao tác vận hành nhiều giai đoạn, tranh chấp tài nguyên với tải foreground và có yêu cầu correctness riêng.

Các nguyên tắc quan trọng nhất:

1. **Tách dữ liệu logic khỏi số byte thực truyền.** Phải tính copy, delta, retry, index/metadata theo đường dữ liệu thật.
2. **Bottleneck quyết định thời gian.** NIC danh nghĩa lớn không có ích khi source read hoặc destination write bị nghẽn.
3. **Dự toán disk theo đỉnh đồng thời.** Giữ bản nguồn, temp files, log retention và compaction có thể khiến peak cao hơn dung lượng cuối.
4. **Tải nền không miễn phí.** Streaming tranh CPU, network, disk, page cache với repair, compaction, backup, index build và foreground.
5. **Cân bằng bytes không đồng nghĩa cân bằng QPS.** Hot key/tenant/range có thể cần thay access pattern, bucket hoặc cache.
6. **Quản lý catch-up và cutover theo protocol của engine.** Copy xong chưa có nghĩa đích đủ điều kiện làm authoritative owner.
7. **Throttle theo SLO và safety**, không tăng concurrency chỉ vì còn node trống.
8. **Giữ replication/failure-domain constraints** trong suốt quá trình, không làm suy giảm độ bền để di chuyển nhanh.
9. **Đo trước, trong và sau:** bytes, lag, disk headroom, p99, cache, compaction, skew và cost.
10. **Hiểu mô hình sản phẩm cụ thể:** MongoDB range migration, Cassandra streaming, Elasticsearch shard relocation, Redis Cluster slot movement và giới hạn kiểm soát của managed services.

**Một kế hoạch cân bằng tốt không chỉ trả lời “mất bao lâu để chuyển dữ liệu”, mà còn chứng minh “trong lúc chuyển, còn đủ băng thông, dung lượng lưu tạm và năng lực xử lý nền để giữ dữ liệu đúng và người dùng vẫn được phục vụ trong giới hạn đã cam kết”.**
