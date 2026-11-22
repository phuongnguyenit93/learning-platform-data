# Phân biệt mất cân bằng dung lượng, lưu lượng và chi phí truy vấn

## 1. Vì sao shard “nóng” chưa cho biết nguyên nhân?

Trong hệ thống NoSQL phân tán, dữ liệu được phân bố lên **node**, **shard**, **partition**, hoặc một đơn vị tương đương tùy sản phẩm. Lý tưởng là không có một thành phần đơn lẻ phải gánh nhiều tài nguyên hơn mức nó có thể phục vụ, trong khi những thành phần khác còn dư khả năng.

Nhưng có ba nguyên nhân mất cân bằng thường bị đánh đồng:

1. **Mất cân bằng dung lượng (storage/data-size skew):** một số node/shard chứa nhiều byte, document hoặc dữ liệu vật lý hơn phần còn lại.
2. **Mất cân bằng lưu lượng (traffic/request-rate skew):** một số node/shard/key nhận nhiều yêu cầu đọc/ghi hơn phần còn lại, dù kích thước dữ liệu không lớn.
3. **Mất cân bằng chi phí truy vấn (query-work/cost skew):** số request có thể ít, nhưng một vài query, index access hoặc mutation tiêu tốn rất nhiều CPU, I/O, bộ nhớ, mạng hoặc công việc nội bộ.

Đây là **ba trục khác nhau**. Một shard chứa nhiều dữ liệu chưa chắc có nhiều người truy cập. Một hot key chỉ có vài byte có thể nhận hàng chục nghìn request/giây. Một query chạy mỗi phút vẫn có thể gây nghẽn nếu nó phải quét lượng dữ liệu khổng lồ và thực hiện aggregation phức tạp.

### 1.1. Bức tranh đầu tiên

Giả sử bốn shard trên các node có cùng năng lực 16 CPU cores:

| Shard | Dữ liệu trên đĩa | Request/giây | CPU trung bình/request | CPU cores tương đương |
|---|---:|---:|---:|---:|
| S1 | 450 GiB | 100 | 4 ms | 0,4 |
| S2 | 150 GiB | 5.000 | 2,8 ms | 14 |
| S3 | 100 GiB | 25 | 450 ms | 11,25 |
| S4 | 100 GiB | 800 | 3 ms | 2,4 |

Các con số chỉ minh họa, coi CPU time/request là công việc CPU của shard; chưa tính các tiến trình nền và các tài nguyên khác.

Có ba kết luận hoàn toàn khác:

- **S1** có nhiều byte nhất, nhưng hiện không phải node bận CPU nhất: nghiêng về **dung lượng**.
- **S2** có QPS cao nhất, mỗi request rẻ nhưng tổng công việc lớn: nghiêng về **lưu lượng**.
- **S3** có QPS rất thấp, mỗi request quá đắt: nghiêng về **chi phí truy vấn**.
- **S4** có tải vừa phải.

Nếu chỉ nhìn “shard nào nhiều GB nhất” rồi di chuyển S1, ta có thể **không giải quyết được CPU saturation của S2/S3**. Nếu chỉ nhìn request rate, ta lại bỏ qua S3.

**Nguyên tắc:** chưa biết tài nguyên nào bị giới hạn và mỗi yêu cầu tiêu tốn bao nhiêu, chưa thể kết luận một shard bị nóng vì nguyên nhân gì.

## 2. Định nghĩa mất cân bằng dung lượng

**Mất cân bằng dung lượng** là sự phân bố không đều của dữ liệu lưu trữ giữa các đơn vị cần so sánh.

Có thể đo bằng:

- Dung lượng dữ liệu logic theo partition/shard;
- Byte dữ liệu vật lý trên đĩa;
- Byte của index, SSTable/segment, metadata;
- Số document/row/item;
- Dung lượng WAL/commit log/tombstone;
- Dung lượng bản sao trên mỗi node;
- Tỷ lệ sử dụng đĩa sau khi trừ headroom cần thiết.

Ví dụ:

~~~text
Cluster có bốn shard cùng năng lực:

S1 ████████████████████  500 GiB
S2 ████                  100 GiB
S3 ████                  100 GiB
S4 ████                  100 GiB
~~~

S1 gánh nhiều dữ liệu hơn, nhưng chưa có bằng chứng nó nhận nhiều request hơn.

### 2.1. Hệ quả phổ biến

Khi một shard quá lớn:

- Disk usage và nguy cơ disk-full tăng.
- Compaction, snapshot, backup, restore hoặc shard movement có thể lâu hơn.
- Rebalance cần chuyển nhiều byte, tạo network/disk I/O.
- Index footprint có thể vượt memory/cache.
- Recovery sau lỗi node mất nhiều thời gian.
- Thời gian scan toàn shard có thể tăng cho một số access pattern.
- Dễ chạm hard limit về partition/document/shard size của sản phẩm nếu có.

Một shard có 500 GiB nhưng hiếm khi đọc có thể chưa chạm CPU limit. Vì vậy cần tách **capacity risk** khỏi **request bottleneck**.

### 2.2. Dung lượng logic khác dung lượng vật lý

Một item nghiệp vụ có payload 1 KiB không nhất thiết chỉ dùng 1 KiB trên disk:

- Có metadata;
- Index phụ;
- SSTable/segment overhead;
- Tombstones và phiên bản cũ;
- Replication;
- Compression;
- Temporary files trong compaction;
- Write-ahead logging;
- Snapshot hoặc backup giữ block.

Khi so sánh, phải dùng **cùng một định nghĩa byte** và ghi rõ có tính bản sao hay không.

### 2.3. Nhiều record không chắc nhiều byte

Một shard có 10 triệu document nhỏ có thể ít byte hơn shard có 100 nghìn document lớn. Chỉ nhìn `documentCount` dễ chẩn đoán sai.

### 2.4. Mất cân bằng dung lượng có thể âm thầm

Một shard lưu dữ liệu lịch sử có kích thước tăng mỗi ngày nhưng read QPS thấp. P99 request hiện tại vẫn tốt, song tới lúc disk gần đầy, hệ cần rebalance hoặc thêm năng lực gấp. Đây là lý do capacity planning cần theo dõi độc lập với latency.

## 3. Định nghĩa mất cân bằng lưu lượng

**Mất cân bằng lưu lượng** là sự không đều về **tốc độ request** hoặc lượng bytes/operations truy cập trên những tài nguyên cần so sánh.

Ví dụ:

~~~text
S1  100 req/s
S2  100 req/s
S3  9.000 req/s  <-- hotspot
S4  100 req/s
~~~

Dữ liệu của S3 có thể nhỏ. Nếu partition key của một “sản phẩm đang viral” luôn route vào S3, một key hoặc một logical partition có thể khiến cả shard nóng.

### 3.1. Không chỉ đo tổng request/giây

Cần tách:

- Read requests/giây;
- Write requests/giây;
- Conditional writes/CAS/transaction attempts;
- Bytes đọc và bytes ghi/giây;
- Request retries/giây;
- Fan-out subrequests/giây;
- Số connections đang hoạt động;
- Hệ số cache hit/miss;
- Request rate theo key, tenant, logical partition, physical shard.

Một hệ ghi 1.000 mutation/giây có thể chịu tải khác nhiều so với 1.000 read cache-hit/giây.

### 3.2. Hot key và hot partition

**Hot key:** một khóa được truy cập đặc biệt nhiều.

~~~text
key product:P100 -> 9.000 req/s
mọi key khác     -> 100 req/s
~~~

**Hot logical partition:** nhiều item chung partition key cùng hút lượng lớn request; ví dụ toàn bộ dữ liệu tenant lớn được route theo `tenantId=T1`.

**Hot physical shard:** đơn vị lưu trữ/điều phối nhận tổng lượng công việc lớn từ nhiều logical partitions hoặc từ một logical partition quá nóng.

Ba khái niệm này có quan hệ nhưng không hoàn toàn tương đương.

### 3.3. Traffic skew có thể theo thời điểm

Ví dụ:

- Một mã giảm giá mở lúc 20:00;
- Sự kiện livestream đưa mọi người đọc cùng sản phẩm;
- Một job ETL quét dữ liệu đúng nửa đêm;
- Tất cả thiết bị IoT ghi bucket “phút hiện tại”;
- Một tenant gửi import lớn trong 15 phút.

Nếu chỉ xem trung bình 24 giờ, một spike 5 phút có thể bị che lấp.

### 3.4. Read hotspot khác write hotspot

Một read-hot key có thể giảm tải bằng cache hoặc tăng nguồn read phù hợp.

Một write-hot key, đặc biệt cần thứ tự hoặc conditional update nghiêm ngặt, **khó chia hơn**: mọi mutation có thể phải phối hợp trên cùng authority/version. Tự nhân bản writable copies có thể làm mất bất biến.

## 4. Định nghĩa mất cân bằng chi phí truy vấn

**Mất cân bằng chi phí truy vấn** xảy ra khi một số queries/operations tiêu tốn tài nguyên vượt trội so với số lượng request của chúng.

Xét hai request:

~~~text
GET document by primary key:
  1 index/key lookup, trả 1 KB

SEARCH toàn collection:
  scan 20 triệu documents
  filter, sort, aggregate
  trả 20 dòng kết quả
~~~

Cả hai đều được tính là **một request** trên dashboard QPS, nhưng lượng công việc rất khác.

### 4.1. Chi phí có nhiều thành phần

Một “query đắt” có thể tiêu tốn:

- CPU time;
- Disk I/O hoặc read amplification;
- Bytes dữ liệu quét;
- Memory cho sort/hash aggregation;
- Network bytes;
- Số shard cần fan-out;
- Số index postings/row/cell duyệt;
- Chi phí deserialize/serialize;
- Lock/transaction contention;
- Số round-trip đến replica;
- Compaction/write amplification do mutation;
- Mức tiêu thụ đơn vị tính phí như RU/RCU/WCU theo sản phẩm.

**Không có một đại lượng “query cost” thống nhất cho mọi NoSQL.** Cần đo trực tiếp tài nguyên đang nghẽn và metric của engine đang dùng.

### 4.2. Một request ít nhưng đắt

~~~text
Shard S1:
  10.000 point reads/s * 0,2 ms CPU ≈ 2 CPU cores

Shard S2:
  20 aggregation/s * 400 ms CPU ≈ 8 CPU cores
~~~

S2 nhận ít request hơn **500 lần** nhưng tiêu CPU cao hơn **4 lần** theo ví dụ này.

Nếu chỉ so QPS, S2 trông “rất rảnh” dù CPU quá tải.

### 4.3. Query cost có thể thay đổi theo input

Cùng endpoint `GET /customer/{id}/orders`:

- Customer nhỏ có 10 đơn;
- Customer lớn có 5 triệu đơn.

Nếu query không có pagination/index hợp lý, cùng một API route có phân phối chi phí rất lệch theo **tenant/customer cardinality**.

### 4.4. Một query rẻ khi ít dữ liệu có thể trở nên đắt theo thời gian

Tháng đầu một collection có 10.000 documents, scan toàn bộ chưa đáng chú ý. Sau hai năm có 200 triệu documents, query tương tự có thể trở thành bottleneck. Điều này nối **dung lượng tăng** với **chi phí truy vấn tăng**, nhưng chúng vẫn là hai nguyên nhân cần đo riêng.

## 5. Ba dạng mất cân bằng có thể cùng tồn tại

Không nên coi ba loại là ba nhóm loại trừ lẫn nhau.

Ví dụ một tenant T1 lớn:

1. Dữ liệu T1 chiếm 60% bytes → **size skew**.
2. T1 phát 50% requests → **traffic skew**.
3. T1 còn chạy các report quét dữ liệu lớn → **query-work skew**.

Cần xác định loại nào đang gây **resource saturation** chính, loại nào chỉ là điều kiện góp phần.

### 5.1. Causal chain

~~~text
Tenant lớn
   |
   +--> nhiều dữ liệu ----------------> disk skew
   |
   +--> nhiều người dùng -------------> traffic skew
   |
   +--> query thiếu index -----------> query-cost skew
                                              |
                                              v
                                    CPU / I/O quá tải
                                              |
                                              v
                                    latency p99 tăng
~~~

Đổi shard key có thể phân tán dữ liệu và requests, nhưng **query thiếu index vẫn đắt**. Tạo index có thể giảm chi phí mỗi request, nhưng một hot key vẫn tập trung hàng chục nghìn writes lên một partition.

### 5.2. Cần kết luận nhiều tầng

Thay vì viết:

> “S3 hot vì shard imbalance.”

hãy viết:

> “S3 chứa 12% dữ liệu, nhận 3% requests, nhưng tiêu 47% read CPU; phần lớn do aggregation `customerSummary` quét trung bình 2,1 triệu documents/request.”

Kết luận thứ hai dẫn tới một hành động cụ thể và có thể đo hiệu quả.

## 6. Đơn vị quan sát: node, shard, partition, key và tenant

Một vấn đề lớn là dashboard đang tổng hợp ở sai cấp độ.

### 6.1. Node

Node có CPU, RAM, disk, network và connection pools vật lý. Nhiều shard trên cùng node dùng chung tài nguyên.

~~~text
Node A:
  Shard 1
  Shard 2
  Shard 3
~~~

CPU node cao không chứng minh cả ba shard đều hot.

### 6.2. Physical shard/partition

Đơn vị phân bố và xử lý nội bộ. Một physical partition có thể chứa nhiều logical partitions. Một node có thể đặt nhiều shard trên cùng disk.

### 6.3. Logical partition

Trong DynamoDB hoặc Cosmos DB, **partition key** biểu diễn nhóm dữ liệu logic; mapping sang physical partitions thay đổi theo dịch vụ và thời gian. Trong Cassandra, partition key quyết định token/replica placement; một partition có thể chứa nhiều clustering rows.

### 6.4. Business key

Một product, customer, room, wallet, order hoặc account cụ thể có thể là hot key.

### 6.5. Tenant

Một khách hàng doanh nghiệp lớn có thể chiếm tài nguyên trên nhiều keys và nhiều shards. “Noisy neighbor” có thể tồn tại dù không có một key đơn lẻ nổi trội.

### 6.6. Query pattern

Cùng một query template có thể chạy trên nhiều shards và làm tất cả nodes chậm. Nếu chỉ soi shard nóng, ta dễ bỏ qua query toàn cluster đang tạo nhiều fan-out.

### 6.7. Bảng ánh xạ

| Quan sát | Cấp độ nên điều tra tiếp | Ví dụ |
|---|---|---|
| Một node CPU cao | Shards, query templates, background tasks trên node | Node A chứa hot shard |
| Một shard QPS cao | Partition/key/tenant distribution | Product P100 viral |
| Dung lượng một shard cao | Partition sizes và skew placement | Một partition lịch sử quá lớn |
| Một endpoint p99 cao | Query plan, input size, fan-out | Report theo tenant |
| Tất cả nodes network cao | Query scatter-gather, replication, rebalancing | Tìm kiếm trên mọi shard |
| Disk usage cao nhưng QPS thấp | Dữ liệu, tombstones, compaction, index | Historical partition |
| Nhiều tenant bị chậm bởi một tenant | Resource budget, rate limit, admission control | Import hàng loạt |

**Điều tra từ triệu chứng ở node xuống mức key/query; không suy từ metric tổng hợp đến nguyên nhân mà chưa tách lớp.**

## 7. Công thức đo độ lệch dung lượng

Giả sử cluster có \(N\) shards cùng năng lực. Với shard \(i\), ký hiệu:

\[
D_i = \text{số byte dữ liệu vật lý hoặc logic của shard }i
\]

Tổng bytes:

\[
D_{\text{total}} = \sum_{i=1}^{N} D_i
\]

Trung bình:

\[
\overline{D} = \frac{D_{\text{total}}}{N}
\]

Một chỉ số trực giác:

\[
S_D = \frac{\max_i D_i}{\overline{D}}
\]

Nếu bốn shards có 450, 150, 100, 100 GiB:

\[
\overline{D}=200\ \text{GiB},\quad S_D=\frac{450}{200}=2.25
\]

Shard lớn nhất chứa dữ liệu gấp 2,25 lần mức trung bình.

### 7.1. Giới hạn của max/average

Tỷ lệ này có thể gây hiểu nhầm khi:

- Node có disk capacity khác nhau;
- Shard replicas không đều;
- Một node đang rebuild;
- Dữ liệu có compression/index overhead khác;
- Shard mới tạo còn chưa nhận dữ liệu;
- Chỉ quan sát một lúc đang rebalance.

Với node không đồng nhất, cần so **usage/available capacity** và mức headroom thay vì bytes tuyệt đối.

### 7.2. Tăng trưởng quan trọng như trạng thái hiện tại

Theo dõi:

\[
growth_i = \frac{\Delta D_i}{\Delta t}
\]

Một shard có 200 GiB nhưng tăng 25 GiB/ngày có thể nguy hiểm hơn shard 350 GiB ổn định nếu node chỉ còn ít đĩa trống.

### 7.3. Đo dung lượng nhiều lớp

Ví dụ:

| Chỉ số | Giải thích |
|---|---|
| Logical payload bytes | Dữ liệu ứng dụng |
| Stored data/index bytes | Dữ liệu và index nội bộ |
| On-disk allocated bytes | Dung lượng file thực |
| Replicated bytes | Tổng dung lượng sau replication |
| Temporary/compaction headroom | Dung lượng cần để bảo trì |
| Backup/snapshot retention | Dung lượng giữ theo chính sách |
| Disk free % | Chỗ trống thực tế |

Không thể lấy dung lượng logic để lập kế hoạch ổ đĩa nếu index/compaction overhead lớn.

## 8. Công thức đo độ lệch lưu lượng

Định nghĩa:

\[
Q_i=\frac{\text{số request đến shard }i}{\Delta t}
\]

Ví dụ:

~~~text
S1 = 100 req/s
S2 = 5000 req/s
S3 = 25 req/s
S4 = 800 req/s
~~~

Trung bình:

\[
\overline{Q}=\frac{100+5000+25+800}{4}=1481.25
\]

Độ lệch theo max/average:

\[
S_Q=\frac{5000}{1481.25}\approx3.38
\]

Nhưng đây vẫn là phép đo **số request**, không phản ánh công việc mỗi request.

### 8.1. Đếm request nào?

Một HTTP request có thể phát sinh nhiều database requests. Một query scatter-gather có thể hỏi 20 shards. Một failed CAS có thể vẫn tiêu read/work. Retry cũng là request mới về mặt tải.

Phải định nghĩa Q:

- External API RPS;
- Database operations per second;
- Replica messages/s;
- Query executions/s;
- Retry attempts/s;
- Scan pages/s;
- Index probes/s.

Nếu dashboard A là HTTP RPS còn dashboard B là database RPC/s, không được so trực tiếp.

### 8.2. Read/write split

\[
Q_i = Q_{i,\text{read}} + Q_{i,\text{write}}
\]

Tuy nhiên, không nên cộng hai loại rồi suy chi phí giống nhau. Cần hiển thị chúng riêng và đo thêm read/write bytes.

### 8.3. Tốc độ byte

Một shard nhận 100 req/s nhưng mỗi request đọc 5 MiB có khoảng 500 MiB/s logical read volume. Shard khác nhận 5.000 req/s, mỗi request đọc 1 KiB, chỉ khoảng 4,9 MiB/s. Request count đảo ngược thứ tự của read volume.

### 8.4. Theo cửa sổ thời gian

Một hot key chỉ bùng nổ trong 30 giây có thể biến mất khi tính trung bình 30 phút. Nên dùng các cửa sổ ngắn và dài:

- 10–60 giây cho spike;
- 5–15 phút cho capacity/autoscaling;
- Giờ/ngày cho chu kỳ tải;
- Tuần/tháng cho xu hướng tăng.

## 9. Công thức đo công việc thay vì chỉ đếm request

Đối với một shard, chia operation thành các nhóm `j`, với:

- \(\lambda_{ij}\): số operation loại `j` trên shard `i` mỗi giây;
- \(c_{ij}\): CPU-seconds trung bình mỗi operation;
- \(W_i\): lượng công việc CPU mỗi giây.

\[
W_i=\sum_j \lambda_{ij}\times c_{ij}
\]

Ví dụ:

~~~text
Shard S2:
  5.000 point reads/s
  0,0028 CPU-s / read

W2 = 5000 * 0,0028 = 14 CPU-s/s
~~~

Nếu node có 16 logical cores có thể dùng cho workload đó, một ước lượng thô cho utilization là:

\[
U_{\text{CPU}}\approx \frac{14}{16}=87.5\%
\]

Cách tính này là một **mô hình giản lược**. CPU scheduling, parallelism, GC, background work và bottleneck khác có thể làm hiệu năng thực tế không tuyến tính.

### 9.1. Shard ít request nhưng rất nặng

~~~text
Shard S3:
  25 queries/s
  0,45 CPU-s / query

W3 = 25 * 0,45 = 11,25 CPU-s/s
~~~

S3 chỉ có 25 QPS nhưng cần khoảng 11,25 CPU cores tương đương. Nếu chỉ nhìn QPS, nhóm vận hành có thể đánh giá sai mức độ nóng.

### 9.2. Công việc theo tài nguyên

Có thể định nghĩa các chỉ số riêng:

\[
W^{CPU}_i,\ W^{IO}_i,\ W^{MEM}_i,\ W^{NET}_i
\]

Không nên cố biến mọi thứ thành một điểm tổng duy nhất khi chưa biết tài nguyên nào hạn chế throughput.

Một query dùng ít CPU nhưng giữ 12 GiB RAM để sort có thể gây OOM dù `W^{CPU}` không lớn.

### 9.3. Tài nguyên theo request phải phân phối theo percentile

Không chỉ tính average cost. Ví dụ:

- 99% requests: 2 ms CPU;
- 1% requests: 2 giây CPU.

Mean có thể tăng nhưng vẫn che mức tail latency và vấn đề fairness. Cần p95/p99 và top expensive query templates.

## 10. Thế nào là “chi phí truy vấn cao”?

### 10.1. Tỷ lệ examined/returned

Trong document database, một metric hữu ích:

\[
amplification = \frac{documentsExamined}{\max(documentsReturned,1)}
\]

Ví dụ query trả 20 documents nhưng phải examine 2 triệu:

\[
\frac{2{,}000{,}000}{20}=100{,}000
\]

Đây là tín hiệu mạnh rằng access path chưa phù hợp, dù không phải mọi trường hợp scan lớn đều sai (ví dụ batch analytics cố ý quét toàn dữ liệu).

### 10.2. Read bytes/response bytes

Nếu query trả 10 KiB nhưng đọc từ disk 100 GiB, chi phí truy vấn có thể nằm ở scan/sort/aggregation.

### 10.3. CPU time vs wall time

- **CPU time**: lượng thời gian xử lý trên CPU;
- **Wall-clock latency**: thời gian người dùng chờ;
- **I/O wait**: thời gian chờ disk/network;
- **Queue time**: thời gian chờ slot/worker;
- **Lock wait**: thời gian chờ tài nguyên đồng thời.

Latency 20 giây không nhất thiết là query đang chạy CPU suốt 20 giây. Nó có thể bị chờ queue vì shard quá tải.

### 10.4. Chi phí tính phí theo database

Một số NoSQL có đơn vị capacity/billing như read/write capacity units hoặc request units. Chi phí này có thể hữu ích để so request, nhưng vẫn phải hiểu định nghĩa và những tính năng đang bật.

**Một request unit không phải một mili-giây CPU**. Không so thẳng RU của Cosmos DB với RCU của DynamoDB hoặc CPU time của Cassandra.

## 11. Các triệu chứng: nhận diện nhanh bằng metric

| Triệu chứng | Khả năng cao | Cần xác minh |
|---|---|---|
| Một shard chiếm 70% disk, QPS bình thường | Dung lượng | Partition sizes, index, SSTables, growth |
| Một key nhận 80% writes, disk bình thường | Lưu lượng | Write QPS/key, conditional conflicts |
| Một endpoint chạy ít nhưng CPU cao | Chi phí truy vấn | Query profile, scan, sort, aggregation |
| Một node CPU cao, tất cả shard QPS tương đương | Chi phí khác/background | Compaction, GC, index maintenance |
| Disk IOPS cao trên node có nhiều tombstones | Có thể query cost và storage overhead | Tombstone scans, compaction |
| Tất cả shards cùng CPU cao khi một báo cáo chạy | Scatter-gather expensive query | Fan-out, coordinator, query profile |
| Disk tăng đều ở một shard, chưa chậm | Dung lượng tích lũy | Key distribution, retention, compression |
| Node nóng sau rebalance dù bytes đã đều | Lưu lượng hoặc query cost | Hot keys, query mix, replica routing |
| Chỉ một tenant làm p99 toàn hệ tăng | Noisy neighbor | Cost/tenant, fair-share budgets |
| Read throughput đột biến khi cache miss | Lưu lượng cộng chi phí truy vấn | Hit ratio, cache stampede, fan-out |

Bảng là **heuristic khởi đầu**, không được dùng thay profile hoặc instrumentation.

## 12. Sai lầm khi chỉ nhìn CPU hoặc p99

### 12.1. CPU cao có nhiều nguyên nhân

- QPS cao;
- Query thiếu index;
- Compaction;
- Index build;
- Garbage collection;
- Encryption/compression;
- Rebalance;
- Replication catch-up;
- Background analytics;
- Logging/serialization.

CPU cao chỉ là **triệu chứng**. Cần xem từng nhóm công việc và phân bố theo shard/query.

### 12.2. p99 cao không chỉ vì query đắt

Một query point lookup vốn rẻ có thể mất 5 giây vì phải đợi queue sau một report lớn. Lúc này cần đo **service time** và **queue time** thay vì tối ưu câu point lookup một cách vô ích.

### 12.3. Hiệu ứng hàng đợi phi tuyến

Khi utilization tiến gần giới hạn, tail latency thường tăng rất nhanh vì thời gian chờ và biến động tải.

~~~text
Tải thấp:    xử lý request ngay
Tải trung:   đôi khi phải xếp hàng
Gần bão hòa: queue dài, p99 tăng mạnh
Quá tải:     timeouts -> retries -> quá tải hơn
~~~

Vì vậy CPU tăng từ 65% lên 90% có thể gây tác động latency lớn hơn tỷ lệ tăng CPU đơn thuần.

### 12.4. Một shard nóng kéo chậm request fan-out

Nếu một query cần dữ liệu từ 10 shards, response cuối cùng có thể phải đợi shard chậm nhất. Khi ấy p99 toàn query có thể bị quyết định bởi **straggler shard**, dù 9 shard khác rất nhanh.

## 13. Đo đúng khi dữ liệu có nhiều replica

Replication làm việc quy kết tải trở nên khó hơn.

### 13.1. Dung lượng nhân bản

Nếu một logical partition có 10 GiB và RF=3, tổng byte vật lý trên cluster có thể lớn hơn 30 GiB sau overhead. Không được lấy tổng physical bytes rồi gọi đó là 30 GiB dữ liệu nghiệp vụ duy nhất.

### 13.2. Read routing

Một hệ có thể cân bằng reads giữa replicas, nhưng:

- Client có read preference;
- Một replica đang bị loại khỏi read path;
- Quorum read động chạm nhiều replicas;
- Query cần leader/authority;
- Region locality khiến reads tập trung vào node gần.

Vì vậy **read-hot replica** chưa chắc đồng nghĩa **hot logical key trên toàn cluster**.

### 13.3. Write amplification

Một write logic có thể tạo:

- Nhiều replica writes;
- WAL/commit log;
- Index updates;
- Compaction work;
- CDC/outbox events.

Nếu đo QPS ứng dụng mà không tính replication/internal IO, có thể bỏ sót chi phí ghi thực tế.

### 13.4. Background work thay đổi bức tranh

Một replica đang rebuild có thể tiêu network/disk cao dù external QPS thấp. Cần phân tách **foreground traffic** và **maintenance traffic**.

## 14. Mất cân bằng do partition key

Partition key quyết định cách dữ liệu và yêu cầu được nhóm/routing. Thiết kế key sai có thể tạo cả ba dạng skew.

### 14.1. Khóa chỉ dùng tenantId

~~~text
PK = tenantId

Tenant T1:  80% dữ liệu
Tenant T2:  10%
Tenant T3:  10%
~~~

T1 có thể trở thành một logical partition quá lớn hoặc quá nóng tùy engine.

### 14.2. Khóa thời gian tăng đơn điệu

~~~text
PK = yyyy-MM-dd
SK = timestamp
~~~

Mọi ghi trong ngày hiện tại có thể tập trung vào một partition/bucket. Ngày hôm qua không còn nóng, dù lượng dữ liệu cũ rất lớn.

~~~text
2026-11-11 : 1 TiB, 0 writes/s
2026-11-12 : 1 TiB, 0 writes/s
2026-11-13 : 1 TiB, 0 writes/s
2026-11-14 : 20 GiB, 50.000 writes/s
~~~

Ở đây **hot write partition chứa ít dữ liệu nhất**.

### 14.3. Range-based distribution và key tăng dần

Nếu shard placement dựa trên các range của một khóa tăng đơn điệu, ghi mới liên tục rơi vào range cuối. Các shard cũ chứa dữ liệu lớn nhưng gần như không nhận writes.

Hash distribution có thể trải đều những khóa đa dạng, nhưng **không giúp chia nhỏ một hot key đơn lẻ** nếu mọi request vẫn tới cùng khóa.

### 14.4. Key có cardinality thấp

Ví dụ partition key chỉ là `status` với ba giá trị `NEW`, `PAID`, `CANCELLED`. Hệ chỉ có ít nhóm logic và một nhóm đông/nóng có thể trở thành hotspot.

### 14.5. Key có cardinality cao nhưng lưu lượng vẫn lệch

`customerId` có hàng triệu giá trị nhưng một khách doanh nghiệp lớn tạo 40% traffic. Nhiều key tổng thể không bảo đảm phân bố request đều.

## 15. Dung lượng một partition khác tổng dung lượng shard

Một shard 500 GiB có thể gồm:

- 500 partitions × 1 GiB;
- 5 partitions × 100 GiB;
- 1 partition × 450 GiB và nhiều partition nhỏ.

Ba cấu trúc cần cách xử lý khác nhau.

### 15.1. Nhiều partition vừa phải

Có thể di chuyển/gán lại logical partitions hoặc rebalancing shards nếu engine hỗ trợ. Việc này thường dễ hơn so với chia nhỏ một key lớn.

### 15.2. Một partition cực lớn

Một logical partition có thể là đơn vị không chia tách tùy engine/API. Di chuyển shard chứa nó sang node khác chỉ **chuyển chỗ vấn đề**, không giảm kích thước chính partition đó.

### 15.3. Chia bucket

Có thể đổi khóa:

~~~text
PK = tenantId
~~~

thành:

~~~text
PK = tenantId + "#" + month
~~~

hoặc:

~~~text
PK = tenantId + "#" + bucketNumber
~~~

Mục tiêu là hạn chế kích thước/tải trên từng partition. Nhưng cách chia cần dựa vào query patterns: nếu thường xuyên đọc **tất cả lịch sử tenant**, query phải fan-out nhiều buckets rồi merge/sort/paginate.

### 15.4. Không chia mà quên invariant

Một counter quota toàn tenant trước đây nằm một item; chia thành 16 counters có thể tăng throughput nhưng **không còn bảo vệ quota tổng** chỉ bằng điều kiện trên từng bucket. Cần allocator/quota reservation hoặc authority chung khi invariant nghiêm ngặt.

## 16. Traffic hotspot theo thời gian: ví dụ IoT

Một hệ lưu telemetries:

~~~text
PK = deviceType + "#" + date
SK = eventTimestamp
~~~

Nếu hàng triệu thiết bị đều gửi dữ liệu vào key ngày hiện tại, write throughput có thể dồn vào một partition.

### 16.1. Thiết kế theo thiết bị

~~~text
PK = deviceId + "#" + date
~~~

Trải writes theo nhiều device IDs, giảm hot partition nếu traffic phân bố đủ rộng.

Nhưng nếu một thiết bị duy nhất gửi hàng trăm nghìn events/giây, key theo device vẫn nóng.

### 16.2. Thêm bucket

~~~text
PK = deviceId + "#" + date + "#" + bucket
bucket = hash(eventId) % 16
~~~

Cách này phân tán writes, nhưng query lịch sử một thiết bị/ngày phải đọc 16 buckets và merge theo timestamp.

### 16.3. Chọn bucket có cơ sở

Quá ít buckets không đủ giảm tải. Quá nhiều buckets tăng read fan-out/metadata và chi phí. Quyết định dựa vào:

- Peak writes/s của một device;
- Năng lực item/partition/shard thực tế;
- Kích thước event;
- Số buckets cần để có headroom;
- Query thường dùng;
- Chi phí fan-out;
- Khả năng thay bucket count theo thời gian.

Không tự chọn `% 16` rồi coi là giải pháp cuối.

## 17. Hot key do read: cache có thể giúp nhưng cần hiểu giới hạn

Giả sử một product được xem 50.000 lần/giây:

~~~text
GET product:P100 -> 50.000 req/s
~~~

Nếu nội dung công khai ít thay đổi, một cache có thể giảm số read xuống nguồn.

### 17.1. Read-through cache

~~~text
Client -> Cache
           |
           +-- hit --> trả dữ liệu
           |
           +-- miss -> NoSQL source -> cache result
~~~

Tỷ lệ hit 99% có thể giảm lượt source read đáng kể trong điều kiện phù hợp. Nhưng cache cũng có thể là hotspot: một Redis key có QPS cao ở một primary vẫn cần phân bố/cache tier đủ năng lực.

### 17.2. Cache stampede

Khi một key hot hết TTL, nhiều request đồng thời cache-miss rồi truy cập nguồn.

~~~text
50.000 request đồng thời
           |
           v
       Cache miss
           |
           +--> 50.000 source reads
~~~

Biện pháp:

- Request coalescing/single-flight;
- Jittered TTL;
- Stale-while-revalidate cho dữ liệu được phép stale;
- Prewarming;
- Local cache với invalidation phù hợp;
- Rate limit;
- Replicate read-only cache theo vùng/edge.

### 17.3. Những dữ liệu không được cache cũ tùy ý

ACL, số dư, reservation cuối cùng và giá chốt giao dịch có yêu cầu khác catalog công khai. Cache không được làm yếu invariant hoặc quyền truy cập khi không có một protocol nhất quán phù hợp.

### 17.4. Không áp read strategy cho write hotspot

Nếu một key nhận 20.000 writes/s, cache thông thường không giúp tránh tranh chấp mutation tại authority. Cần thiết kế khác, chẳng hạn queue theo key, batching hoặc sharded counter với quy tắc tổng hợp.

## 18. Write hotspot: chọn giải pháp theo invariant

### 18.1. Counter có thể tổng hợp

Một view counter có thể chia:

~~~text
views:P100:bucket:0
views:P100:bucket:1
...
views:P100:bucket:15
~~~

Mỗi request tăng một bucket, phép đọc tổng:

\[
views(P100)=\sum_{b=0}^{15} views_b
\]

Phù hợp nếu business chấp nhận độ trễ tổng hợp/chi phí đọc và không cần một số đếm linearizable duy nhất trong mọi thời điểm.

### 18.2. Counter hạn mức nghiêm ngặt

Nếu mỗi lần sử dụng voucher phải đảm bảo tổng `used <= 1000`, việc chia 16 buckets với điều kiện cục bộ `used_b < 1000` **không bảo vệ tổng**.

Có thể cần:

- Quota allocator cấp trước token cho buckets;
- Authority giữ hạn mức toàn cục;
- Transaction/conditional write trên aggregate;
- Reservation ledger và reconciliation;
- Một mô hình admission control khác phù hợp.

### 18.3. Workflow cần thứ tự

Nếu mọi cập nhật của Order O100 cần thứ tự trạng thái, một single-writer queue theo orderId có thể giảm CAS contention, nhưng phải xử lý rebalance, duplicate delivery, idempotency và stale consumer.

### 18.4. Giảm contention trước khi tăng shard

Một hot lock/unique claim không thể giải quyết chỉ bằng thêm nodes nếu mọi request phải tranh một key. Cần:

- Giảm số attempts/retries;
- Debounce/aggregate tại nguồn;
- Batching hợp lệ;
- Fair queue;
- Backoff với jitter;
- Phân tách business operations nếu invariant cho phép.

## 19. Query cost skew do thiếu index

Một nguyên nhân phổ biến của query chậm không phải số shard mà là **đường truy cập sai**.

### 19.1. Ví dụ MongoDB

Collection `orders` có nhiều document:

~~~json
{
  "_id": "O100",
  "tenantId": "T1",
  "customerId": "U42",
  "createdAt": "2026-11-14T09:00:00Z",
  "status": "PAID",
  "amountMinor": 250000
}
~~~

Query:

~~~javascript
db.orders.find({
  tenantId: "T1",
  customerId: "U42",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(50);
~~~

Nếu chỉ có index trên `_id`, engine có thể phải examine nhiều documents và sort tốn tài nguyên.

Một index được thiết kế theo pattern cụ thể có thể là:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1
});
~~~

Index này chỉ **minh họa hướng thiết kế**; cần xét selectivity, workload reads/writes, index size và các query khác.

### 19.2. Xem explain thay vì đoán

~~~javascript
db.orders.find({
  tenantId: "T1",
  customerId: "U42",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(50)
  .explain("executionStats");
~~~

Quan sát:

- `nReturned`;
- `totalDocsExamined`;
- `totalKeysExamined`;
- Winning plan;
- Các bước scan/sort;
- Execution time theo kết quả thực nghiệm.

Cần lưu ý kế hoạch và metrics có thể biến đổi theo phiên bản, cache/warm state và dữ liệu thử nghiệm.

### 19.3. Thêm index có chi phí

Index mới:

- Tăng disk footprint;
- Tăng RAM pressure/cache;
- Tăng write amplification;
- Tốn thời gian index build;
- Có thể ảnh hưởng peak write throughput;
- Không giúp mọi query khác nếu predicate/sort không khớp.

Đây là ví dụ sửa **query-work skew** có thể làm **storage skew** tăng thêm. Sau tối ưu phải đo lại cả ba trục.

## 20. Query cost skew do scans và filters trong DynamoDB

DynamoDB tổ chức truy cập theo khóa. Một thiết kế không phù hợp có thể dùng `Scan` cho câu hỏi đáng lẽ cần `Query` theo access pattern.

### 20.1. Ví dụ schema

~~~text
Table Orders
PK = tenantId
SK = orderId
~~~

Muốn tìm 50 đơn PAID mới nhất của một tenant, nếu schema chỉ có sort key `orderId` ngẫu nhiên, filter theo status và sort theo createdAt có thể dẫn tới đọc nhiều item rồi xử lý phía ứng dụng.

### 20.2. FilterExpression không thay key design

Trong DynamoDB, `FilterExpression` của Query/Scan được áp dụng **sau khi dữ liệu đã được đọc theo operation**, vì vậy không nên kỳ vọng một filter bỏ 99,9% kết quả sẽ giúp giảm read capacity tương ứng.

Một access pattern có thể cần:

- Composite sort key hợp lý;
- GSI cho đường truy cập khác;
- Bảng materialized view theo trạng thái/thời gian;
- Partition/bucket phù hợp;
- Pagination và giới hạn kết quả.

### 20.3. RCU/WCU và hot partition

Cần xem cùng lúc:

- Consumed read/write capacity;
- Throttled requests;
- Logical partition key popularity;
- Item sizes;
- GSI write amplification;
- Traffic spikes;
- Query/Scan shape.

Adaptive capacity hoặc cơ chế split for heat của dịch vụ có thể hỗ trợ **một số dạng nóng**, nhưng **không nên mặc định** một single key nóng vô hạn sẽ tự được phân nhỏ trong khi vẫn giữ một aggregate có conditional invariants.

### 20.4. Một GSI có thể tạo hotspot riêng

Bảng chính phân bố khá đều, nhưng GSI dùng partition key `status="NEW"` có cardinality rất thấp; mọi đơn mới cùng cập nhật phần index liên quan. **Cân bằng bảng chính không chứng minh index phụ cũng cân bằng**.

## 21. Cassandra: wide partition, ALLOW FILTERING và tombstones

### 21.1. Wide partition là vấn đề dung lượng

Ví dụ:

~~~sql
CREATE TABLE events_by_tenant (
    tenant_id text,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (tenant_id, event_time, event_id)
);
~~~

Một tenant T1 có hàng tỷ events trong cùng partition. Partition này có thể quá lớn và nhiều reads theo time range trở nên nặng.

### 21.2. Bucketing theo thời gian

Một phương án:

~~~sql
CREATE TABLE events_by_tenant_day (
    tenant_id text,
    event_date date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, event_date),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id ASC
);
~~~

Partition key gồm `tenant_id, event_date`. Điều này giới hạn dữ liệu mỗi partition theo ngày, phù hợp nếu queries thường truy cập theo ngày hoặc một khoảng nhỏ. Với tenant rất lớn, có thể vẫn cần thêm bucket.

### 21.3. Query không phù hợp schema

Một CQL query cần lọc theo trường không nằm trong access path có thể phải scan/filter lượng dữ liệu lớn hoặc bị database từ chối nếu không được phép. Dùng `ALLOW FILTERING` để ép query chạy không làm chi phí biến mất.

### 21.4. Tombstone-heavy reads

Một partition có nhiều deletes/expired TTL có thể chứa nhiều tombstones. Query phải duyệt chúng trong một số read path, dẫn tới chi phí I/O/CPU lớn dù số row trả về ít.

Điều này khác với vấn đề “nhiều request”. Một query rất hiếm gặp nhưng đi qua nhiều tombstones có thể cực chậm.

### 21.5. Compaction là background cost

Khi dữ liệu liên tục được ghi/xóa, compaction có thể tiêu disk/CPU/network nội bộ. Shard/node nóng không nhất thiết do một query cụ thể, mà do **write amplification và lifecycle storage**.

Không tự chữa bằng cách tăng số partition hoặc giảm `gc_grace_seconds` tùy tiện; phải xem model xóa, repair safety và compaction strategy.

## 22. Elasticsearch/OpenSearch: lệch shard và truy vấn scatter-gather

Search engine phân phối index thành shards. Cần tách:

- Shard nào có nhiều documents/bytes;
- Shard nào nhận nhiều search/index operations;
- Query nào có aggregate/sort/scoring đắt;
- Có bao nhiêu shard tham gia mỗi search.

### 22.1. Data skew

Một index có shards quá chênh lệch dung lượng có thể phục hồi/rebalance khó. Phân tích shard placement, routing và số lượng index/segments.

### 22.2. Traffic skew

Nếu ứng dụng dùng custom routing theo tenant và tenant T1 cực nóng, phần lớn truy vấn có thể đến một shard tương ứng, dù dữ liệu toàn index được cân bằng.

### 22.3. Work skew

Một query aggregation trên field có cardinality cao, một sort/score script đắt, hoặc deep pagination có thể tiêu CPU/heap và ảnh hưởng latency toàn shard.

### 22.4. Fan-out cost

~~~text
Search request
    |
    +--> Shard 1
    +--> Shard 2
    +--> Shard 3
    +--> ...
    +--> Shard 40
    |
  Coordinator merge results
~~~

Một HTTP request có thể phát sinh 40 shard-level search operations. QPS ở API thấp không có nghĩa tổng shard work thấp.

### 22.5. Hướng xử lý

- Dùng routing đúng khi access pattern cho phép;
- Giới hạn query complexity;
- Tối ưu filters, aggregations và sort;
- Dùng pagination phù hợp như search_after/PIT theo yêu cầu;
- Pre-aggregate các metric lớn;
- Xem query profiling và slow logs;
- Đánh giá số shard/size hợp lý theo workload;
- Không mở rộng số shard vô hạn vì mỗi shard cũng có overhead.

Không nên gọi `force_merge` hoặc đổi shard count trên production như một cách chữa nóng tức thời khi chưa hiểu cost và rủi ro.

## 23. Redis: big key và hot key là hai vấn đề khác nhau

### 23.1. Big key

Một key chứa danh sách/hashes/sets rất lớn có thể gây:

- Chi phí memory;
- Block hoặc latency khi thực hiện operation tốn kém;
- Network lớn khi trả toàn key;
- Khó di chuyển/evict;
- Slow command khi thao tác theo kích thước dữ liệu.

### 23.2. Hot key

Một key nhỏ như:

~~~text
product:P100:summary -> 600 bytes
~~~

nhưng được GET 100.000 lần/giây vẫn có thể làm nóng node phụ trách slot.

### 23.3. Big + hot

Nếu một key vừa chứa 50 MiB vừa bị GET liên tục, tải network và serialization có thể cực cao.

### 23.4. Chẩn đoán khác nhau

- Với big key: xem kích thước value/encoding, pattern access, partial retrieval, chia cấu trúc hoặc TTL/lifecycle.
- Với hot key: xem ops/s theo key, cache replicas, local caches, read fanout và rate limiting.
- Với command đắt: xem Slow Log/latency diagnosis và độ phức tạp thao tác; một operation O(N) trên collection lớn có thể là query-work skew.

Redis Cluster phân tán keys theo hash slots; một hot key không tự được chia qua nhiều nodes chỉ vì cluster có thêm node.

## 24. Một ví dụ đồ thị: supernode không nhất thiết là nhiều truy vấn

Với graph database, một node có hàng triệu cạnh (*supernode*) có thể tạo chi phí traverse lớn.

~~~text
User U1 --follows--> Celebrity C
User U2 --follows--> Celebrity C
...
Millions of edges
~~~

Nếu query:

~~~text
Tìm toàn bộ neighbors của Celebrity C
~~~

nó có thể tiêu nhiều I/O, CPU và memory dù chỉ chạy vài lần/giờ.

Đây có thể đồng thời là:

- Data skew ở adjacency list;
- Query-cost skew vì traversal nở rộng;
- Traffic skew nếu celebrity node được truy cập rất thường xuyên.

Giải pháp gồm giới hạn depth/fan-out, traversal predicates, pagination, precomputed recommendations hoặc thay mô hình dữ liệu tùy engine. Không nên chỉ thêm graph nodes rồi hy vọng supernode tự biến mất.

## 25. Nhận diện traffic skew từ workload thực

### 25.1. Phân bố top keys

Không chỉ đếm tổng:

~~~text
Total: 100.000 RPS
~~~

hãy xem:

~~~text
Top key product:P100:  40.000 RPS
Top key product:P101:  12.000 RPS
All others:            48.000 RPS
~~~

Một key chiếm 40% traffic là tín hiệu đáng quan tâm, nhất là nếu nó route vào một shard không dễ chia.

### 25.2. Top tenants

~~~text
T1: 70% RPS
T2: 10%
T3: 5%
Remaining: 15%
~~~

Đây có thể là noisy-neighbor issue ngay cả khi mỗi key của T1 không quá nóng.

### 25.3. Hot key vs hot range

Với range-based placement, một đoạn keys liên tiếp (ví dụ timestamp gần hiện tại) có thể nóng, không phải một key. Cần heatmap theo ranges/token buckets thay vì chỉ top key.

### 25.4. Skew metrics cần tránh nổ cardinality

Không nên gắn `userId` hoặc `orderId` của hàng triệu giá trị làm label trực tiếp lên mọi Prometheus metric; điều đó gây bùng nổ time-series.

Có thể:

- Thu thập top-k heavy hitters bằng streaming/sampling;
- Ghi hashed/truncated key trong diagnostic logs có kiểm soát;
- Dùng histogram và per-shard counters;
- Lưu top tenants đã được kiểm soát;
- Dùng distributed tracing với sampling.

Tuân thủ quy tắc bảo mật và không đưa PII trực tiếp vào log chỉ để chẩn đoán hotspot.

## 26. Heatmap ba chiều: shard × thời gian × loại tải

Một bảng tổng có thể che nguyên nhân. Heatmap giúp thấy khi nào và ở đâu tải tập trung.

~~~text
                 Thời gian (mỗi ô = 5 phút)
             10:00  10:05  10:10  10:15  10:20

Shard S1      low    low    low    low    low
Shard S2      low    HOT    HOT    HOT    low
Shard S3      med    med    med    med    med
Shard S4      low    low    HOT    low    low
~~~

Tạo heatmap riêng cho:

- Disk bytes/capacity;
- Read QPS;
- Write QPS;
- CPU seconds/giây;
- Read bytes/giây;
- Query examined/returned;
- p99 latency;
- Queue depth;
- Throttling;
- Compaction backlog.

### 26.1. Coi chừng heatmap chỉ dùng số tuyệt đối

Nếu các nodes có CPU/disk capacity khác nhau, phải xem **percentage of usable capacity** và normalized saturation, không chỉ request count.

### 26.2. Liên hệ sự kiện nghiệp vụ

Gắn thời điểm xảy ra:

- Marketing campaign;
- Product launch;
- Tenant import;
- Scheduled export;
- Index rebuild;
- Deployment;
- Rebalancing;
- Cache invalidation;
- Incident/failover.

Một hotspot xảy ra đúng lúc ETL chạy có thể do job scan, không phải traffic khách hàng tăng.

## 27. Quy trình chẩn đoán: từ triệu chứng đến nguyên nhân

### Bước 1 — Xác nhận có saturation thật không

Đo CPU, disk IOPS/latency, memory, GC, network, connections, request queue, throttling và latency. Xác định tài nguyên nào chạm trần trước.

### Bước 2 — Chọn đúng cấp độ so sánh

Node, shard, logical partition, business key, tenant hay query template? Đừng so một node có 8 shards với node chỉ có 1 shard mà không chuẩn hóa.

### Bước 3 — Tách ba trục

Ghi cho từng đơn vị:

~~~text
DataBytes
ReadOpsPerSecond
WriteOpsPerSecond
CPUSecondsPerSecond
ReadBytesPerSecond
Scan/ExaminedPerReturned
P95/P99Latency
BackgroundWork
~~~

### Bước 4 — Phân nhóm truy vấn

Top query templates theo:

- Tổng CPU time;
- Tổng disk read;
- Tổng RU/capacity units;
- Request count;
- p99 latency;
- Scan amplification;
- Lock wait;
- Fan-out count.

Một query 0,1% RPS có thể chiếm 50% CPU.

### Bước 5 — Tìm nguyên nhân từ query plan và key distribution

- Index sai/chưa có?
- Partition key monotonic/hot?
- Tenant siêu lớn?
- Query không có limit?
- Sort/aggregation spill?
- Scan qua tombstones?
- GSI hot?
- Cache stampede?
- Retry storm?
- Compaction/repair/rebalance?

### Bước 6 — Đề xuất giải pháp theo loại skew

Chỉ chọn hành động sau khi có bằng chứng phân biệt size, traffic và query cost.

### Bước 7 — Kiểm chứng với workload đại diện

Đo trước/sau theo đủ ba trục, kiểm tra invariant và tail latency. Không đánh giá chỉ bằng “disk đều hơn” nếu p99 vẫn xấu.

## 28. Bảng quyết định xử lý đúng loại mất cân bằng

| Nguyên nhân chính | Cách xử lý thường hợp lý | Điều phải đánh đổi |
|---|---|---|
| Một shard chứa quá nhiều partitions vừa phải | Rebalance/reshard/move partitions | Network I/O, thời gian di chuyển, headroom |
| Một logical partition quá lớn | Bucketing/splitting theo access pattern | Read fan-out, migration, ordering |
| Key range tăng đơn điệu | Hash/salt/time bucket phù hợp | Range queries phức tạp hơn |
| Một key read-hot | Cache/replicated read path, request coalescing | Staleness, invalidation |
| Một key write-hot | Batching, single writer, sharded counters nếu hợp lệ | Ordering, global invariant, read aggregation |
| Một tenant phát quá nhiều requests | Rate limit, fair-share, tenant isolation | Throughput/latency của tenant lớn |
| Query scan nhiều data | Index/schema redesign, selective query | Index storage, write amplification |
| Aggregation/sort đắt | Preaggregation, result limits, query controls | Freshness, storage, workflow |
| Scatter-gather toàn cluster | Routing/pruning, query-specific index | Schema/index complexity |
| Background compaction quá tải | Data lifecycle/compaction tuning/capacity | IO budget, tombstone safety |
| Cache-miss bùng nổ | Prewarming, coalescing, TTL jitter | Dữ liệu cũ có giới hạn, cache overhead |
| Retry storm | Backoff/jitter, idempotency, admission control | Thời gian chờ và throughput khi lỗi |

Không áp cùng một giải pháp cho mọi hàng: **data movement không chữa query plan xấu**, còn **thêm index không tự chia một hot write key**.

## 29. Rebalance dữ liệu: chữa đúng loại skew nào?

### 29.1. Khi nào hữu ích?

Nếu shard S1 có 500 GiB và S2/S3/S4 mỗi shard 100 GiB, đồng thời hạ tầng cho phép phân chia và di chuyển dữ liệu ở cấp phù hợp, rebalancing có thể:

- Giảm disk pressure;
- Tăng headroom;
- Rút ngắn recovery cho những đơn vị cụ thể;
- Cân bằng data distribution;
- Giảm rủi ro node-full.

### 29.2. Khi nào không hữu ích?

Nếu shard S2 có 50.000 read/s vào một key nhỏ duy nhất, chuyển shard S2 sang node khác chỉ **chuyển điểm nóng**. Thêm nodes không tự chia một key thành nhiều independent write authorities.

### 29.3. Rebalance có chi phí thực

- Streaming nhiều dữ liệu qua mạng;
- CPU và disk reads;
- Ghi dữ liệu vào đích;
- Compaction/reindex;
- Tác động p99;
- Khả năng thiếu headroom khi di chuyển;
- Read/write routing thay đổi;
- Quản lý trạng thái migration và rollback.

Không kích hoạt rebalance ồ ạt giữa giờ cao điểm nếu không biết resource budget.

### 29.4. Thêm nodes không phải lúc nào tăng throughput

Nếu bottleneck là một single-key conditional update hoặc một global lock, thêm 20 nodes có thể không làm tăng throughput nhiều. Cần xử lý **serialization point**.

## 30. Tối ưu truy vấn: chữa cost skew mà không phá write path

### 30.1. Index và projection

Một query `orders_by_customer` có thể được tối ưu bằng bảng đọc/secondary index được thiết kế trước thay vì quét toàn bộ `orders_by_id`.

Nhưng một projection cập nhật async cần:

- CDC/outbox;
- Event ordering;
- Idempotency;
- Version guard;
- Backfill/rebuild;
- Freshness SLO;
- Reconciliation.

### 30.2. Preaggregation

Thay vì tính doanh thu mỗi lần mở dashboard:

~~~text
SCAN 100 triệu orders
GROUP BY tenant, day
~~~

có thể duy trì `daily_revenue_by_tenant` theo sự kiện hoặc batch.

Ưu điểm: query thường nhanh và rẻ. Đánh đổi: dữ liệu tổng hợp có thể chậm, cần sửa khi event đến muộn, refund hoặc duplicate.

### 30.3. Pagination và giới hạn kết quả

Không cho một query trả hàng triệu rows vào API đồng bộ khi người dùng chỉ cần 50 dòng. Dùng pagination/keyset/continuation token phù hợp.

Nhưng pagination **không tự tạo snapshot nhất quán** giữa các trang; nếu dữ liệu đang đổi, cần snapshot/query consistency theo yêu cầu.

### 30.4. Giới hạn query complexity

Có thể áp:

- Maximum lookback;
- Max rows;
- Max aggregation buckets;
- Allowed sort fields;
- Timeout;
- Memory/cost budget;
- Admission control cho các báo cáo lớn;
- Async export thay vì request trực tiếp.

Không để một query tùy ý của tenant làm nghẽn thao tác quan trọng của tenant khác.

### 30.5. Cân bằng index và write cost

Mỗi index có thể giảm read query cost nhưng tăng write amplification và storage. Tối ưu phải dựa trên **tổng workload**, không chỉ một câu query trong isolation.

## 31. Query fan-out: chi phí bị nhân trên nhiều shard

Giả sử một query tìm sản phẩm có filter không gắn được với shard key và phải gửi tới 32 shards:

~~~text
API request: 1
      |
      +--> 32 shard search tasks
      |
      +--> merge/sort 32 result sets
      |
      +--> return 20 products
~~~

QPS API=100 có thể tạo hàng nghìn shard-level operations mỗi giây.

### 31.1. Scatter-gather đắt khi nào?

- Fan-out nhiều shard;
- Mỗi shard phải scan rộng;
- Coordinator merge/sort nhiều kết quả;
- Một shard chậm kéo p99 lên;
- Có network cross-region;
- Partial failures/retries tạo thêm requests.

### 31.2. Hướng giảm

- Có routing theo tenant/partition trong query;
- Partition pruning;
- Index phù hợp filter;
- Top-k pushdown khi engine hỗ trợ;
- Precomputed materialized views;
- Đưa báo cáo toàn cluster sang đường async/OLAP;
- Giới hạn concurrency.

Không tự hash mọi key nếu hệ cần range scans qua nhiều shards; phải đánh đổi read locality.

## 32. Noisy neighbor: mất cân bằng chi phí theo tenant

Trong hệ multi-tenant, một tenant lớn có thể ảnh hưởng các tenant nhỏ ngay cả khi dữ liệu nằm trên nhiều shards.

Ví dụ:

~~~text
Tenant T1: 20 QPS báo cáo rất nặng
Tenant T2: 500 QPS point reads
Tenant T3: 300 QPS point reads
~~~

T1 có thể dùng 80% CPU dù chỉ chiếm 2,4% tổng QPS.

### 32.1. Chia ngân sách theo tài nguyên tiêu tốn

Một rate limit chỉ theo RPS có thể không công bằng. Có thể cần:

- Cost-based admission control;
- RU/CPU budget theo tenant;
- Concurrency limits;
- Query timeouts;
- Batch job isolation;
- Weighted fair queuing;
- Dedicated capacity cho tenants lớn.

### 32.2. Ưu tiên isolation có cơ sở

Chuyển T1 sang shard/node riêng có thể hữu ích nếu workload T1 đủ lớn và chi phí cô lập hợp lý. Nhưng phải xét replication, data movement, vận hành và khả năng phát sinh một hot key nội bộ.

### 32.3. Không đo tenant bằng PII không cần thiết

Dùng tenant identifier kỹ thuật, hashed labels hoặc top-k aggregation thích hợp; hạn chế log khóa nhạy cảm vào telemetry.

## 33. Khi nào chi phí truy vấn biến thành mất cân bằng lưu lượng?

Một query chậm dẫn tới timeout ở client. Client retry:

~~~text
Query đắt (2s)
      |
   timeout
      |
 client retry x3
      |
query workload x4
      |
 CPU tăng, queue dài
      |
 timeout nhiều hơn
~~~

Ban đầu là **query-cost skew**, nhưng retry storm làm tăng **request-rate skew**.

Cần phá vòng lặp:

- Dùng deadline hợp lý;
- Retry chỉ khi an toàn và cần thiết;
- Exponential backoff với jitter;
- Retry budget;
- Circuit breaker;
- Query admission control;
- Cancel query khi client hủy nếu engine hỗ trợ;
- Idempotency cho operations có side effect.

Giải pháp tốt không chỉ tăng CPU, vì một query bị gọi lặp không giới hạn vẫn có thể nuốt mọi capacity.

## 34. Kịch bản A: shard to nhưng không nóng về request

Cluster có bốn shard:

~~~text
Shard   Stored GiB   Read RPS   Write RPS   CPU
S1         480          50          10       15%
S2         160         900         200       60%
S3         160         850         190       58%
S4         160         920         210       62%
~~~

### 34.1. Chẩn đoán

S1 có storage cao gấp ba, nhưng traffic và CPU thấp. Đây chủ yếu là **data-size skew**, có thể do nhiều dữ liệu lịch sử hoặc partition key/range placement.

### 34.2. Hành động

- Xác định dữ liệu nào làm S1 lớn;
- Kiểm tra partition size distribution;
- Xem retention/TTL/archive;
- Đánh giá reshard/rebalance;
- Xác định disk headroom và recovery time;
- Không di chuyển dữ liệu chỉ vì ratio nếu quá trình di chuyển gây rủi ro lớn hơn.

### 34.3. Hành động không trực tiếp giải quyết

Thêm cache read không xử lý 480 GiB trên đĩa. Tạo index mới có thể **làm vấn đề dung lượng tệ hơn**.

## 35. Kịch bản B: shard ít dữ liệu nhưng một hot key

~~~text
Shard   Stored GiB   Read RPS   Write RPS   CPU
S1         150         100          20       10%
S2         150       25000          30       95%
S3         150         120          25       12%
S4         150         110          22       11%
~~~

Top key trên S2: `product:P100` có 23.000 read/s.

### 35.1. Chẩn đoán

Dung lượng đều; **read traffic** lệch rất lớn. Không phải data-size skew.

### 35.2. Hướng xử lý

Nếu product P100 là dữ liệu public, ít thay đổi:

- Local/edge cache;
- Request coalescing;
- Jittered TTL;
- Replica-read distribution phù hợp;
- Prewarming trước campaign;
- Rate limits khi client spam;
- Theo dõi cache stampede.

### 35.3. Điểm phải lưu ý

Nếu field đang đọc là inventory khả dụng tại thời điểm checkout, không được lấy cache cũ thay authoritative reservation. Tách **catalog read path** khỏi **inventory commit path**.

## 36. Kịch bản C: ít request nhưng query cực đắt

~~~text
Shard   Stored GiB   RPS   CPU   Dominant query
S1         200       200   22%  point reads
S2         200       150   25%  point reads
S3         200        15   93%  report aggregation
S4         200       210   24%  point reads
~~~

S3 có 15 QPS nhưng một số query quét 8 triệu documents/request.

### 36.1. Chẩn đoán

Dung lượng đều, RPS thấp, chi phí mỗi query cực lớn. Đây là **query-work skew**.

### 36.2. Hành động

- Dùng explain/profile;
- Xem examined/returned;
- Tìm index phù hợp;
- Giới hạn time range;
- Preaggregate report;
- Chuyển report sang worker/OLAP;
- Giới hạn concurrency và memory;
- Đo scan/CPU trước-sau.

### 36.3. Hành động dễ sai

Chia thêm shard có thể làm mỗi query quét nhiều nơi hơn, tăng coordinator/fan-out overhead. Không phải cứ thêm shards là query sẽ nhanh.

## 37. Kịch bản D: cả ba cùng xuất hiện sau migration

Một tenant lớn được chuyển sang một partition key chỉ gồm `tenantId`. Sau migration:

- Dữ liệu T1 dồn vào partition lớn;
- T1 nhận 60% write traffic;
- Query `GET /tenants/T1/events` không giới hạn ngày, quét toàn bộ lịch sử;
- Compaction backlog tăng;
- p99 write và read cùng xấu.

### 37.1. Cách tách nguyên nhân

1. Data bytes/partition → xác nhận oversize.
2. Write RPS/partition → xác nhận hot writer.
3. Query plan và bytes scanned/query → xác nhận query quá rộng.
4. Compaction I/O → xem đây là hậu quả hay bottleneck độc lập.
5. Cùng lúc so p99 với queue time.

### 37.2. Thiết kế mới

Có thể cần:

~~~text
PK = tenantId + day + bucket
SK = eventTime + eventId
~~~

kèm query thời gian, chỉ đọc một số days/buckets, pagination, preaggregation.

### 37.3. Cẩn thận đọc toàn bộ lịch sử

Việc chia tenant thành 365×16 buckets làm query “đọc mọi thứ” phải fan-out rất lớn. Nên chuyển truy vấn lịch sử toàn bộ sang **async export/analytics** thay vì ép vào API realtime.

### 37.4. Không phá invariant

Nếu trước đây một item chứa quota toàn tenant, tách dữ liệu events khỏi quota authority; không chia quota mà bỏ bảo vệ giới hạn tổng.

## 38. Một quy trình điều chỉnh shard key an toàn

### 38.1. Xác định access patterns trước

Liệt kê những truy vấn thật:

- Point read theo ID;
- Read theo tenant + khoảng thời gian;
- Latest N events;
- Aggregation ngày/tháng;
- Conditional update;
- Delete/TTL;
- Cross-tenant analytics.

### 38.2. Chọn key đáp ứng cả read và write

Một key chỉ tối ưu phân bố write có thể làm read fan-out tăng. Một key tối ưu một query range có thể tập trung toàn bộ write ngày hiện tại. Cần chọn trade-off theo SLO.

### 38.3. Phân tích cardinality và heavy hitters

Trước migration, kiểm tra:

- Số distinct partition keys;
- Tỷ lệ requests trên top 1/top 10 keys;
- Kích thước p50/p95/p99 partition;
- Growth rate theo key;
- Query cost theo key;
- Dự báo campaign/seasonality.

### 38.4. Kế hoạch dữ liệu

- Backfill từ nguồn có checkpoint;
- Dual-write nếu có protocol idempotent;
- Version/sequence reconciliation;
- Read comparison;
- Cutover theo tenant hoặc phần trăm traffic;
- Rollback route;
- Xóa cấu trúc cũ sau khi xác nhận đầy đủ.

Không bật dual-write rồi giả định hai hệ luôn đồng bộ; phải xử lý crash giữa hai writes và thứ tự events.

### 38.5. Đo sau migration

Trước khi tuyên bố giải quyết xong, đo:

- Max/avg size;
- Max/avg read/write QPS;
- Query CPU/IO per request;
- Fan-out;
- p95/p99;
- Cost;
- Replication/rebalance backlog;
- Business invariant.

## 39. Resource saturation và khả năng phục vụ thực tế

Một node có 32 cores và trung bình sử dụng 80% CPU chưa chắc lành mạnh nếu có spike 100% kéo dài. Một node có CPU chỉ 30% cũng có thể bị nghẽn disk latency hoặc network.

### 39.1. Những loại bottleneck thường gặp

| Bottleneck | Dấu hiệu |
|---|---|
| CPU-bound | CPU cao, run queue tăng, CPU-time/query lớn |
| Disk I/O-bound | IOPS/throughput cao, await lớn, cache miss |
| Memory-bound | Heap pressure, GC, spill, OOM |
| Network-bound | Throughput sát giới hạn, retransmit, cross-region latency |
| Lock/serialization-bound | Conflict, wait, low CPU nhưng throughput kẹt |
| Coordinator-bound | Fan-out/merge/connection pool bão hòa |
| Storage-capacity-bound | Disk free thấp, compaction thiếu headroom |
| Throttle/quotas | Throttling dù node không luôn full CPU |
| Background-work-bound | Repair/rebalance/compaction chiếm tài nguyên |

Cần biết tài nguyên nào gây latency. Chỉ dùng CPU% để gọi “hotspot” có thể sai.

### 39.2. Nút cổ chai có thể di chuyển

Thêm index giảm CPU scan nhưng tăng writes/index maintenance. Chia partition giảm hot writes nhưng tăng read fan-out. Cache giảm source read nhưng làm tăng Redis/edge egress. Rebalancing giảm disk skew nhưng tạo network spikes tạm thời.

Vì vậy quy trình tối ưu là **đo → sửa một nguyên nhân có bằng chứng → đo lại tổng thể**.

## 40. SLO và mục tiêu cân bằng không chỉ là “mọi shard bằng nhau”

Không cần các shard có số byte hoặc QPS **giống hệt nhau**. Mục tiêu hợp lý hơn là:

- Không có đơn vị nào vượt resource budget quá lâu;
- Có headroom cho failover/replication;
- p95/p99 đáp ứng SLO;
- Không để tenant này làm hại tenant khác vượt mức chấp nhận;
- Query cost dự đoán được;
- Rebalance/recovery đủ nhanh;
- Invariant nghiệp vụ vẫn đúng;
- Chi phí hạ tầng phù hợp.

Một hệ có max/avg data-size skew 1,5 nhưng dư disk và p99 ổn định có thể không cần migration tốn kém. Ngược lại, một hot write key 1 KiB gây 40% request failures phải được xử lý khẩn dù storage distribution hoàn hảo.

### 40.1. Một số SLO minh họa

- p99 `GET /products/{id}` dưới ngưỡng sản phẩm chấp nhận ở tải đại diện;
- Tỷ lệ request bị throttled dưới mức mục tiêu theo tenant;
- Không có oversell sau concurrent reservations;
- Dung lượng disk còn đủ headroom cho một lần failover/rebuild;
- Query report không làm tăng checkout p99 vượt ngưỡng;
- Sau khi chuyển shard, resource skew không vượt ngưỡng vận hành lâu dài.

Các ngưỡng cụ thể phải chọn từ thực đo và yêu cầu kinh doanh, không lấy một con số mẫu làm tiêu chuẩn chung.

## 41. Monitoring và cảnh báo có hành động

### 41.1. Bộ metric tối thiểu

| Nhóm | Metric | Phạm vi |
|---|---|---|
| Dung lượng | Physical/logical bytes, disk free, growth | Node, shard, partition |
| Phân bố | Max/avg size, top partition sizes | Cluster/shard |
| Lưu lượng | Read/write ops/s, bytes/s | Node, shard, key/tenant top-k |
| Throttling | Rejected/throttled operations | Partition, tenant, endpoint |
| Cost | CPU-ms/query, read bytes, scan/returned, RU | Query template, shard |
| Tail latency | p50/p95/p99, queue time | Endpoint, query, node |
| Cache | Hit/miss, stampede, hot keys | Cache tier |
| Nền | Compaction, repair, rebalance, GC | Node/shard |
| Query fan-out | Shards queried/request, merge time | Query template |
| Fairness | Cost/RPS theo tenant, queued/rejected | Tenant |
| Business | Oversell, duplicate claims, consistency errors | Workflow |

### 41.2. Chỉ báo sớm

- Top partition growth cao;
- Một key chiếm phần lớn read/write;
- Query examined/returned tăng;
- Scan bytes/query tăng nhanh theo dữ liệu;
- Cache hit ratio giảm khi campaign;
- p99 của một tenant tăng trước toàn hệ;
- Throttled capacity theo shard;
- Compaction backlog chưa giảm sau peak.

### 41.3. Tránh cardinality explosion

Metric labels quá chi tiết làm hệ quan sát trở thành hotspot khác. Dùng aggregation/top-k, logs/traces sampled và dữ liệu bảo mật theo policy.

## 42. Kiểm thử phân bố tải với workload đại diện

### 42.1. Test data-size skew

- Tạo tập key có phân bố giống sản phẩm thật;
- Có tenants lớn/nhỏ;
- Có document sizes đa dạng;
- Theo dõi mapping shards và growth;
- Thử delete/TTL/compaction;
- Đánh giá thời gian di chuyển/rebuild.

### 42.2. Test traffic skew

- Phân bố Zipfian hoặc heavy-hitter phù hợp;
- Bursts trong 30–60 giây;
- Hot read key;
- Hot write key;
- Read/write mix;
- Multi-tenant noisy neighbor;
- Retry storm có kiểm soát.

Không chỉ dùng uniformly random keys: workload đều giả có thể làm shard key sai trông như hoạt động rất tốt.

### 42.3. Test query-work skew

- Point lookup;
- Range query;
- Sort;
- Aggregation;
- Multi-shard scatter-gather;
- Hot tenant report;
- Tombstone-heavy read;
- Query không đủ index;
- Query có input cardinality lớn.

### 42.4. Test cả ba đồng thời

Production không chạy từng nhóm tách biệt. Một ETL scan có thể xảy ra đúng lúc flash sale tạo hot read và maintenance rebalance. Test phối hợp giúp phát hiện resource contention.

### 42.5. Quan sát kết quả

Đo p95/p99, queue time, CPU/IO, disk free, throttling, rejected requests, business correctness. Nếu target chỉ là “100.000 RPS”, test có thể vẫn bỏ sót rằng toàn bộ RPS đang đến một key.

## 43. Bài tập thực hành

### Bài tập 1 — Phân loại ba shard

~~~text
S1: 600 GiB, 100 RPS, CPU 15%
S2: 100 GiB, 9.000 RPS, CPU 92%
S3: 100 GiB, 20 RPS, CPU 88%
~~~

**Câu hỏi:** S1, S2, S3 lần lượt gợi ý loại mất cân bằng nào?

**Gợi ý:** S1 dung lượng; S2 lưu lượng; S3 nhiều khả năng chi phí mỗi query/background work, cần profile để xác nhận.

### Bài tập 2 — Tính storage skew

Bốn shards có 500, 100, 100, 100 GiB.

**Câu hỏi:** `max/average` là bao nhiêu?

**Gợi ý:** Trung bình 200 GiB; ratio 2,5.

### Bài tập 3 — Tính traffic skew

Bốn shards có 1.000, 1.000, 1.000, 5.000 req/s.

**Câu hỏi:** `max/average` là bao nhiêu?

**Gợi ý:** Trung bình 2.000; ratio 2,5.

### Bài tập 4 — Tổng công việc CPU

Shard A nhận 2.000 req/s, mỗi request dùng 2 ms CPU. Shard B nhận 20 req/s, mỗi request dùng 300 ms CPU.

**Câu hỏi:** Shard nào dùng nhiều CPU-seconds/s?

**Gợi ý:** A: 4 CPU-s/s; B: 6 CPU-s/s. B ít request hơn nhưng đắt hơn.

### Bài tập 5 — Không nên tự cho rằng data-size skew gây CPU

Một node có 80% bytes cluster nhưng CPU 5%, node khác 10% bytes nhưng CPU 95%.

**Câu hỏi:** Có nên ưu tiên di chuyển data từ node đầu để giảm CPU node hai?

**Gợi ý:** Chưa đủ bằng chứng. Cần xác định requests/query patterns của node hai.

### Bài tập 6 — Hot key

Một key 1 KiB nhận 40.000 reads/s.

**Câu hỏi:** Đây là big key hay hot key?

**Gợi ý:** Hot key; value nhỏ không ngăn request hotspot.

### Bài tập 7 — Big key

Một Redis key 100 MiB chỉ được đọc một lần/ngày, nhưng mỗi lần GET gây network spike.

**Câu hỏi:** Đây là size skew, traffic skew hay query-operation cost?

**Gợi ý:** Big key và chi phí một operation lớn; traffic theo request count thấp.

### Bài tập 8 — MongoDB explain

Query trả 50 documents nhưng `totalDocsExamined=5.000.000`.

**Câu hỏi:** examined/returned ratio là bao nhiêu và nên kiểm tra gì?

**Gợi ý:** 100.000; xem index, predicate, sort, range, explain plan.

### Bài tập 9 — DynamoDB FilterExpression

Một Query đọc nhiều item rồi filter còn 0,1%.

**Câu hỏi:** Vì sao filter không tự giảm chi phí read theo 0,1%?

**Gợi ý:** Filter được áp dụng sau phần đọc theo operation; cần key condition/index phù hợp.

### Bài tập 10 — GSI skew

Bảng chính phân bố đều, GSI partition key chỉ có ba giá trị status.

**Câu hỏi:** Có thể GSI hot không?

**Gợi ý:** Có. Index phụ có key distribution và write access pattern riêng.

### Bài tập 11 — Cassandra wide partition

Một tenant có hàng tỷ events trong partition theo tenantId.

**Câu hỏi:** Chia theo tenant + day giải quyết điều gì, tạo chi phí gì?

**Gợi ý:** Giảm size/traffic tập trung mỗi partition nhưng tăng số partitions và read fan-out cho truy vấn lịch sử dài.

### Bài tập 12 — Time-series hot partition

PK là ngày hiện tại, mọi IoT device ghi vào cùng ngày.

**Câu hỏi:** Vì sao shard ngày nay nóng dù chứa ít byte hơn các ngày cũ?

**Gợi ý:** Write traffic tập trung theo thời gian; storage size và traffic khác nhau.

### Bài tập 13 — Sharded counter

Một voucher có quota 1.000, bạn chia `used` thành 16 counters.

**Câu hỏi:** Đặt điều kiện `usedBucket < 1000` có bảo vệ tổng quota không?

**Gợi ý:** Không. Cần authority/allocation để bảo vệ tổng.

### Bài tập 14 — Search fan-out

100 search requests/s, mỗi request hỏi 24 shards.

**Câu hỏi:** Có thể tạo ra bao nhiêu shard-level search tasks/s trong mô hình đơn giản?

**Gợi ý:** Khoảng 2.400 tasks/s trước retries và những công việc khác.

### Bài tập 15 — Cache stampede

Một sản phẩm viral hết TTL, 20.000 clients cùng miss cache.

**Câu hỏi:** Cơ chế nào giúp tránh đẩy toàn bộ tải sang source?

**Gợi ý:** Single-flight, coalescing, TTL jitter, prewarm và stale-while-revalidate nếu dữ liệu được phép cũ.

### Bài tập 16 — Query cost vs CPU utilization

Một query chỉ chạy 10 lần/phút nhưng mỗi lần phải scan 100 GiB dữ liệu.

**Câu hỏi:** Nếu node I/O cao, có chắc do lưu lượng request lớn không?

**Gợi ý:** Không; số request thấp nhưng work/operation cực cao.

### Bài tập 17 — Rebalance không hết hotspot

Bạn di chuyển shard chứa hot key từ node A sang node B. Node B sau đó CPU 98%.

**Câu hỏi:** Vì sao?

**Gợi ý:** Bạn chuyển điểm nóng thay vì chia workload; cần sửa read cache, write serialization hoặc partitioning.

### Bài tập 18 — Thiết kế dashboard

Dashboard chỉ có CPU node, disk bytes và HTTP RPS tổng.

**Yêu cầu:** Nêu tối thiểu năm metric bổ sung để phân biệt ba loại skew.

**Gợi ý:** QPS/shard, top keys, bytes/query, CPU-ms/query, query examined/returned, background compaction, queue time, throttling.

### Bài tập 19 — Query mới làm index lớn hơn

Sau khi thêm index, report nhanh hơn nhưng disk S1 tăng 20% và writes chậm hơn.

**Câu hỏi:** Đây có phải tối ưu sai?

**Gợi ý:** Chưa chắc; cần đo trade-off read latency, storage headroom, write amplification và SLO tổng.

### Bài tập 20 — Noisy neighbor

Tenant T1 chỉ phát 5% requests nhưng dùng 75% CPU của query pool.

**Câu hỏi:** Rate limit thuần theo RPS có đủ không?

**Gợi ý:** Có thể không. Cần cost-based quotas, concurrency isolation hoặc async reports.

### Bài tập 21 — SLO khi toàn hệ cân bằng GB

Mọi shard chứa 250 GiB, nhưng một shard bị throttled 30% writes.

**Câu hỏi:** Kết luận “đã balance” có chính xác không?

**Gợi ý:** Chỉ cân bằng dung lượng; vẫn có traffic/cost hotspot.

### Bài tập 22 — Truy vấn báo cáo lịch sử

Bạn thêm bucket theo ngày để phân bố writes. Report “mọi thời gian” giờ phải đọc 365 buckets và sort/merge.

**Câu hỏi:** Bước thiết kế nào bị bỏ sót?

**Gợi ý:** Query access patterns và cost of fan-out; cần preaggregation/async analytics hay đường truy cập khác.

### Bài tập 23 — Hot partition và QUORUM

Một partition cần CAS/transaction cho business invariant. Team đề xuất nhân bản độc lập writable copies để chia load.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** Vi phạm order/uniqueness/quota nếu không có giao thức authority/coordination phù hợp.

### Bài tập 24 — Thay đổi thời gian quan sát

Một shard có 30.000 QPS trong 30 giây mỗi giờ, còn lại 100 QPS.

**Câu hỏi:** Vì sao trung bình giờ có thể che vấn đề?

**Gợi ý:** Spike ngắn làm queue/throttling/p99 tăng; cần window ngắn và percentile.

### Bài tập 25 — Case study cuối

Cluster có các triệu chứng:

- S1 disk 90% nhưng CPU 20%;
- S2 read QPS 15 lần median;
- S3 chỉ 1% RPS nhưng 45% tổng CPU từ report;
- Tối thứ Sáu cache hit giảm mạnh và timeout tăng.

**Yêu cầu:** Lập kế hoạch điều tra và ba nhóm sửa độc lập.

**Gợi ý:** S1 là capacity/data skew; S2 traffic hotspot; S3 query-cost skew; cache stampede hoặc read miss làm tải nguồn tăng vào khung thời gian sự kiện. Đo per-shard/key/query rồi mới chọn rebalance, caching, query optimization.

## 44. Checklist trước khi thay đổi hệ thống production

- [ ] Có bằng chứng tài nguyên nào bị saturation trước.
- [ ] Đã tách storage skew, request skew và query-cost skew.
- [ ] Đã đo cùng cấp độ node/shard/partition/key/tenant.
- [ ] Đã tách read traffic khỏi write traffic.
- [ ] Đã phân biệt external RPS và internal shard operations.
- [ ] Có top-k hot keys/ranges và top tenants.
- [ ] Có query profiles và cost distribution, không chỉ average latency.
- [ ] Có scan amplification và read/write bytes metrics.
- [ ] Có dữ liệu theo thời gian cao điểm, không chỉ 24h average.
- [ ] Đã xem ảnh hưởng replication, quorum và read routing.
- [ ] Đã loại trừ background compaction, repair, rebalance, index build.
- [ ] Nếu đổi partition key, đã liệt kê mọi access pattern và invariant.
- [ ] Nếu sharding counter, đã xác nhận có/không có global quota.
- [ ] Nếu thêm index, đã dự trù disk/write amplification.
- [ ] Nếu cache hot key, đã thiết kế TTL/invalidation/stampede protection.
- [ ] Nếu di chuyển shards, đã dự trù streaming/I/O và rollback.
- [ ] Nếu tối ưu aggregation, đã đo freshness/consistency của projection.
- [ ] Có quota/fairness để tenant lớn không làm hại tenant nhỏ.
- [ ] Có test workload skew và concurrency, không chỉ random-uniform.
- [ ] Có kiểm tra business correctness sau migration.
- [ ] Có p95/p99, throttling, error rate và resource headroom trước/sau.
- [ ] Không kết luận “đã cân bằng” chỉ vì số GiB trên mọi shard bằng nhau.

## 45. Tổng kết

Trong NoSQL, **mất cân bằng dung lượng**, **mất cân bằng lưu lượng** và **mất cân bằng chi phí truy vấn** là ba vấn đề liên quan nhưng khác nhau:

- **Dung lượng:** *Dữ liệu nằm ở đâu và chiếm bao nhiêu tài nguyên lưu trữ?* Đo bytes, partition sizes, index footprint, disk headroom và growth. Hướng xử lý có thể là rebalancing, retention, bucketing hoặc đổi mô hình dữ liệu.
- **Lưu lượng:** *Bao nhiêu thao tác đang truy cập khóa/partition/shard nào?* Đo read/write QPS, request bytes, top keys, burst và throttling. Hướng xử lý có thể là cache, request coalescing, phân bố keys, batching, single writer hoặc rate limits.
- **Chi phí truy vấn:** *Mỗi thao tác thực sự làm bao nhiêu việc?* Đo CPU-ms, bytes scanned, examined/returned, RU, sort/aggregation, fan-out và background work. Hướng xử lý là index/query plan, preaggregation, giới hạn query, schema theo access pattern và cô lập workload nặng.

Một shard có nhiều dữ liệu không chắc bận; một hot key có thể rất nhỏ; một report chạy rất ít lần có thể ngốn gần hết CPU. Thêm node, di chuyển shard hay tạo index chỉ hiệu quả khi chúng **đánh đúng nguyên nhân** và không gây một loại skew khác nặng hơn.

**Nguyên tắc cuối cùng:** trước khi “cân bằng” một cụm NoSQL, hãy đo riêng **dữ liệu phân bố thế nào, yêu cầu đi tới đâu, và mỗi yêu cầu tiêu tốn bao nhiêu công việc**. Sau đó chọn thay đổi ít phức tạp nhất vẫn bảo vệ đúng bất biến nghiệp vụ, độ trễ và năng lực phục hồi của hệ thống.

