# Theo dõi dung lượng, tốc độ tăng trưởng và tải đĩa

## 1. Mở đầu: vì sao “đĩa còn 25%” chưa đủ để kết luận an toàn?

Một hệ thống dùng **NoSQL database** lưu đơn hàng, lịch sử hoạt động và read model cho ứng dụng Java. Dashboard báo:

~~~text
Cluster capacity:         12 TiB
Total disk used:           9 TiB
Cluster free:              3 TiB (25%)
Current write throughput:  18.000 events/s
API read p99:             110 ms
~~~

Nhìn thoáng qua, người vận hành có thể cho rằng còn rất nhiều dung lượng. Nhưng khi phân tích theo node:

~~~text
Node A: 93% full
Node B: 78% full
Node C: 54% full
Node D: 71% full

Node A:
  hot partition: tenant-7
  compaction pending: high
  disk write latency: increasing
  snapshot/repair planned tonight
~~~

Một node có thể sắp hết chỗ trước khi tỷ lệ trung bình của cluster vượt 75%. Khi Node A phải compaction, nó có thể cần **dung lượng tạm thời cho tệp đầu ra** trong khi tệp đầu vào vẫn còn. Vì vậy hệ có thể phát sinh write stalls hoặc failure ngay cả khi cluster nhìn chung còn 3 TiB.

Ngoài ra, tải đĩa có thể đạt giới hạn IOPS/throughput trước khi dung lượng đầy: **free space và disk performance là hai trục khác nhau**.

Bài học **“Theo dõi dung lượng, tốc độ tăng trưởng và tải đĩa”** thuộc chương **“Quan sát và chẩn đoán”** trong module **Database No SQL**. Mục tiêu là xây cách đo, dự báo và phản ứng có bằng chứng, thay vì chỉ quan sát một gauge `disk_used_percent`.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt logical data size, physical allocated size, filesystem used/free và usable capacity.
2. Tính dung lượng với compression, replication, indexes, versions, tombstones, logs, snapshots và compaction.
3. Theo dõi dung lượng theo node, shard/partition, table/collection, tenant và storage tier.
4. Dự báo **growth rate, days-to-threshold** và disk headroom cho maintenance/failover.
5. Hiểu IOPS, bandwidth, I/O latency, queue depth, busy time và cách đọc p95/p99.
6. Phân biệt tải foreground read/write với compaction, GC, backup, repair, rebalance và index build.
7. Thiết kế metric dashboard/PromQL có đơn vị, nhãn, cửa sổ thời gian và alert hợp lý.
8. Nhận diện các điểm khác nhau giữa Cassandra, MongoDB, Redis, DynamoDB, Elasticsearch, RocksDB và Couchbase.
9. Instrument Java client với Micrometer mà không nhầm request latency với physical disk latency.
10. Lập capacity plan, runbook, fault injection tests và ngưỡng vận hành theo SLO.

---

## 2. Bốn câu hỏi khác nhau cần dashboard trả lời

| Câu hỏi | Metric phù hợp | Vì sao không thay thế nhau? |
|---|---|---|
| **Bao nhiêu dữ liệu đang tồn tại?** | Live/logical bytes, item count, index bytes | Logical bytes chưa bao gồm replication, compaction |
| **Bao nhiêu dung lượng đang bị chiếm?** | Filesystem used/allocated, snapshots, WAL, SSTables | Có thể tăng dù live data giảm |
| **Khi nào chạm ngưỡng nguy hiểm?** | Growth rate, forecast, headroom, days-to-threshold | 80% dùng nhưng đứng yên khác 60% tăng rất nhanh |
| **Đĩa có theo kịp I/O không?** | Read/write IOPS, MiB/s, latency, queue, saturation | Đĩa còn trống vẫn có thể throttle |

Một hệ có 90% disk used nhưng write rate thấp, không compaction debt, có kế hoạch mở rộng có thể ít khẩn cấp hơn hệ 65% used nhưng tăng 5% mỗi giờ và sắp chạy repair.

### 2.1. Dung lượng là *stock*, tốc độ tăng là *flow*

- **Stock:** bao nhiêu bytes đang chiếm tại thời điểm T.
- **Flow:** bao nhiêu bytes/giây hoặc GiB/ngày thay đổi.
- **Latency:** mỗi operation mất bao lâu.
- **Throughput:** mỗi giây có bao nhiêu I/O operations hoặc bytes được xử lý.

Không dùng `ops/s` làm “dung lượng còn lại”, cũng không dùng `disk_free_bytes` để suy SSD đủ đáp ứng tải.

### 2.2. Đường đi của một write

~~~mermaid
flowchart LR
    A["Java application"] --> B["NoSQL request"]
    B --> C["WAL / journal"]
    B --> D["Memtable / cache"]
    D --> E["SSTables / pages / segments"]
    E --> F["Compaction / merge"]
    C --> G["Disk / filesystem"]
    E --> G
    F --> G
    F -. "extra read/write I/O" .-> B
    H["Indexes / replication / backup"] --> G
~~~

Đây là **sơ đồ khái quát**. Không phải mọi NoSQL dùng WAL, memtable và SSTable cùng lúc. Chẳng hạn Redis chủ yếu là in-memory, MongoDB WiredTiger có cơ chế B-tree/checkpoint, còn DynamoDB là managed service không công bố cùng các bộ đếm disk host.

---

## 3. Các loại dung lượng: đừng trộn mẫu số

### 3.1. Logical live data

Kích thước của tập dữ liệu **đang có ý nghĩa đối với ứng dụng**.

Ví dụ một collection có 10 triệu documents, trung bình 1 KiB payload logic:

\[
D_{\text{logical}}\approx10\,000\,000\times1\text{ KiB}
\approx9.54\text{ GiB}.
\]

Kích thước này chưa tính BSON/JSON representation, metadata, index, compression, replicas hoặc tệp cũ.

### 3.2. Serialized data

Khi chuyển từ object Java sang BSON/JSON/Protobuf hoặc native storage representation, dung lượng có thể khác với payload text gốc. Field names, metadata và encoding ảnh hưởng.

### 3.3. Compressed data

Nếu engine nén dữ liệu, có thể định nghĩa tỷ lệ:

\[
r_c=\frac{D_{\text{compressed}}}{D_{\text{uncompressed}}},
\]

với \(0<r_c\) thường nhỏ hơn 1 cho dữ liệu nén tốt. Nếu `r_c=0.4`, 100 GiB trước nén cần khoảng 40 GiB sau nén ở lớp được đo.

Không phải mọi index/WAL/metadata đều có tỷ lệ nén tương tự.

### 3.4. Physical allocated / storage bytes

Bao gồm các tệp hiện đang dùng bởi engine như data files, indexes, journals/WAL, tombstones, obsolete versions, segment merges, temporary files và đôi khi snapshots theo cách thống kê.

### 3.5. Filesystem used và available

Filesystem có thể dùng bytes bởi:

- Database.
- Logs.
- Snapshots/backups.
- OS/system.
- Temporary files.
- Các tệp đã bị unlink nhưng process vẫn mở.
- Reserved blocks và filesystem metadata.

**Filesystem available cho service** có thể nhỏ hơn free blocks theo thống kê do reserved capacity hoặc quota.

### 3.6. Provisioned vs usable capacity

Ổ/volume được cấp phát 1 TiB không có nghĩa ứng dụng có thể dùng an toàn đủ 1 TiB. Cần trừ:

- OS/filesystem overhead.
- Watermark/headroom policy.
- Compaction/merge temporary space.
- Backup/snapshot headroom.
- Failover/rebalance allowance.
- Burst buffer và sai số dự báo.

---

## 4. Dung lượng logic khác dung lượng vật lý như thế nào?

| Thành phần | Tác động đến số bytes | Ví dụ |
|---|---|---|
| Payload | Dữ liệu nghiệp vụ hiện hành | Document, row, value |
| Serialization/metadata | Thêm overhead | Field names, headers, checksums |
| Compression | Thường giảm bytes một số lớp | Snappy/LZ4/Zstd theo engine |
| Secondary indexes | Thêm bytes và I/O ghi | MongoDB index, GSI, search index |
| Replication | Nhiều copies trên nodes/regions | RF=3, multi-region |
| MVCC/history | Giữ versions cũ trong một giai đoạn | Snapshot readers, history store |
| Tombstones/TTL | Dữ liệu đã xóa còn metadata | Cassandra tombstone |
| WAL/journal | Log phục hồi | Commit log, journal |
| Compaction/merge | Input và output có thể cùng tồn tại tạm | LSM SSTables, Lucene segments |
| Backup/snapshot | Có thể tăng chiếm chỗ, tùy hardlink/dedup | Local snapshots |
| Rebalance | Temporary copies/data streaming | Shard migration/bootstrap |
| Free fragments | Không gian tái sử dụng nội bộ | Storage file chưa trả về OS |

### 4.1. Mô hình sizing ban đầu

Một mô hình minh họa:

\[
D_{\text{physical,cluster}}
\approx
(D_{\text{logical}}\times r_c+ D_{\text{index,per-copy}}
+D_{\text{overhead,per-copy}})\times RF
+D_{\text{logs}}+D_{\text{snapshots}}+D_{\text{temporary}}.
\]

**Không dùng công thức này như định luật của mọi NoSQL**: một số indexes/metadata không nhân RF giống payload, storage có erasure coding/tiered storage hoặc cross-region replicas, còn số liệu đã được vendor tính sẵn replication có thể gây double-count.

### 4.2. Ví dụ

~~~text
Logical dataset:                 500 GiB
Compression ratio (estimate):   0.45
Index + metadata per copy:       60 GiB
Replication factor:                  3
Local logs/snapshots/temp:      170 GiB (entire cluster)
~~~

Ước tính:

\[
D\approx(500\times0.45+60)\times3+170
=1025\text{ GiB}.
\]

Đây mới là **estimate ban đầu**. Sau khi hệ hoạt động, phải đối chiếu physical storage metrics, disk overhead và peak maintenance.

### 4.3. Replication vừa tăng dung lượng vừa ảnh hưởng fault tolerance

Không được giảm replication chỉ để chữa disk pressure nếu chưa đánh giá consistency, availability và durability. Thêm replica cũng có thể tạo bootstrap/streaming load tạm thời.

---

## 5. Space amplification và write amplification

### 5.1. Space amplification

Một cách định nghĩa trong một phạm vi rõ:

\[
SA=\frac{\text{Physical bytes currently occupied}}{\text{Logical live bytes}}.
\]

Nếu logical live data = 100 GiB nhưng data/obsolete versions đang chiếm 180 GiB, \(SA\approx1.8\) trong phạm vi đo.

Tử số có thể tính/không tính index, replication và snapshot theo báo cáo. **Ghi rõ phạm vi để so hai hệ không sai.**

### 5.2. Write amplification

\[
WA=\frac{\text{Physical storage bytes written}}{\text{Logical bytes written}}.
\]

Một ghi logic có thể viết WAL rồi SSTable rồi bị compaction lại, thêm index/replica writes tùy phạm vi.

### 5.3. Số logical bytes không đổi nhưng disk used vẫn tăng

Các nguyên nhân thường gặp:

- Updates liên tục tạo old versions.
- Compaction chưa bắt kịp.
- TTL expired nhưng physical cleanup chưa xong.
- Snapshot giữ files cũ.
- Long-running transactions/snapshots cản thu hồi versions.
- Index mới/backfill.
- Logs retention tăng.
- Deleted files còn được process mở.
- Backup local chưa rotate.

### 5.4. Một delete không luôn giải phóng disk tức thì

MongoDB có thể tái dùng free space nội bộ; Cassandra giữ tombstones tới lúc GC/compaction phù hợp; Elasticsearch giữ deleted-doc markers trong segments cho tới merge; DynamoDB TTL cleanup bất đồng bộ.

Không phát cảnh báo “DELETE failed” chỉ vì disk bytes không giảm ngay. Phải đo đúng semantics cleanup.

---

## 6. Tốc độ tăng trưởng: từ dữ liệu theo ngày tới dự báo

Cho \(D(t)\) là bytes đang chiếm trên một scope nhất định.

Tốc độ tăng quan sát:

\[
g=\frac{D(t_2)-D(t_1)}{t_2-t_1}.
\]

Nếu \(D\) đo GiB, thời gian đo ngày, \(g\) có đơn vị **GiB/ngày**.

### 6.1. Ví dụ

~~~text
2026-11-01 00:00:  1.20 TiB
2026-11-08 00:00:  1.34 TiB
~~~

Tăng:

\[
\Delta D=0.14\text{ TiB}\approx143.36\text{ GiB}
\]

trong 7 ngày, tức trung bình khoảng 20.48 GiB/ngày.

### 6.2. Không chỉ lấy hai mẫu bất kỳ

Một đợt compaction có thể làm physical used giảm mạnh, còn snapshot làm tăng tạm. Nếu lấy đúng hai mốc ở hai pha khác nhau, growth rate có thể gây hiểu nhầm.

Nên nhìn:

- 1 giờ: phát hiện burst.
- 24 giờ: vận hành.
- 7 ngày: xu hướng tuần.
- 30 ngày: mùa vụ/growth nền.
- Giai đoạn peak/campaign và retention expiry.
- Physical-vs-logical divergence.

### 6.3. Net growth và gross writes

**Gross logical writes** là tổng bytes ghi mới/cập nhật. **Net storage growth** là tăng physical bytes sau deletes/TTL/compaction.

Một hệ có 500 GiB ghi mỗi ngày nhưng xóa/reclaim gần tương đương có thể net storage tăng thấp. Tuy nhiên disk I/O vẫn rất cao.

### 6.4. Growth dự báo cần ghi giả định

Giả sử \(g\) tuyến tính ổn định. Nếu write rate tăng 10%/tuần, extrapolation tuyến tính từ tháng trước sẽ thiếu capacity. Nên dùng nhiều scenarios và diễn giải từng giả định.

---

## 7. Tính days-to-threshold

Đặt:

- \(C\): dung lượng usable trong scope.
- \(u\): ngưỡng sử dụng tối đa vận hành, ví dụ 0.75.
- \(D_0\): dung lượng hiện đã chiếm.
- \(g>0\): tăng trưởng ròng GiB/ngày.

Dung lượng tại ngưỡng:

\[
D_{\text{threshold}}=uC.
\]

Thời gian tới ngưỡng theo mô hình tuyến tính:

\[
T=\frac{uC-D_0}{g}.
\]

### 7.1. Ví dụ

~~~text
Usable node capacity:      2.0 TiB = 2048 GiB
Operational threshold:     75%
Currently occupied:        1250 GiB
Net growth:                25 GiB/day
~~~

Ngưỡng:

\[
0.75\times2048=1536\text{ GiB}.
\]

Còn:

\[
1536-1250=286\text{ GiB}.
\]

Số ngày:

\[
T=286/25=11.44\text{ ngày}.
\]

**Chỉ còn khoảng 11,4 ngày tới ngưỡng an toàn đặt ra**, dù filesystem chưa đầy.

### 7.2. Nếu \(g\le0\)

Không chia cho 0 hoặc công bố “vô hạn ngày an toàn”. Có thể nói: *trong cửa sổ đo này chưa có xu hướng tăng tuyến tính*, nhưng cần xét peak, snapshots, repair, TTL và seasonal growth.

### 7.3. Nếu ngưỡng đã bị vượt

`T <= 0` là trạng thái đã chạm hoặc vượt, cần xử lý ngay theo severity policy, không report là âm số ngày một cách khó hiểu.

### 7.4. Ngưỡng không phải luôn 75%

Elasticsearch có disk watermarks; Cassandra và các storage engines có headroom khác nhau; managed service quotas có quy tắc khác. Chọn ngưỡng dựa trên **compaction/recovery requirement của chính deployment**, không sao chép số ví dụ thành config production.

---

## 8. Dự báo nhiều kịch bản, không phụ thuộc một đường thẳng

Một plan nên có ít nhất:

| Kịch bản | Growth assumption | Khi nào dùng |
|---|---|---|
| Bình thường | Trung bình 30 ngày | Kế hoạch capacity nền |
| Peak mùa vụ | Tăng 2–3 lần theo chiến dịch | Bảo vệ event/high-traffic season |
| Burst ingest | Batch import/CDC replay | Giới hạn disk tạm |
| Maintenance overlap | Compaction + backup + repair | Tính peak temporary bytes |
| Một node mất | Rebalance/replication trên nodes còn lại | Capacity khi suy giảm |
| Retention thay đổi | TTL kéo dài, legal hold | Tăng live-set |
| Compression giảm | Dữ liệu ít nén hơn | Storage growth tăng |
| Index migration | Dual indexes/collections | Cần space trong rollout |

### 8.1. Linear vs exponential growth

Nếu số khách tăng \(r\) mỗi tháng, data net growth có thể phụ thuộc tổng users và retention; không tự dùng công thức exponential cho mọi dataset. Data giới hạn theo TTL có thể tiến tới plateau nếu arrival rate ổn định.

### 8.2. Giới hạn theo TTL

Nếu arrival rate ổn định \(a\) bytes/ngày, retention \(R\) ngày và dữ liệu được xóa/thu hồi đều, logical live-set xấp xỉ:

\[
D_{\text{live}}\approx aR.
\]

Nhưng actual physical disk có thể cao hơn do tombstones, GC delay, indexes, compression và snapshots.

### 8.3. Ví dụ retention đổi

Data ingest 40 GiB/day:

- Giữ 30 ngày → logical live set khoảng 1200 GiB.
- Giữ 60 ngày → khoảng 2400 GiB.

Bỏ qua compression/replication, tăng retention gấp đôi có thể gần như tăng live-set gấp đôi trong trạng thái ổn định. Cần capacity review trước khi đổi policy.

---

## 9. Không được chỉ xem trung bình toàn cluster

Một node 95% used có thể gây outage dù trung bình 65%.

### 9.1. Theo node

Theo dõi:

~~~text
node_id
zone / availability domain
total, available, used
growth GiB/day
disk read/write throughput
IOPS and latency
compaction/repair backlog
```

### 9.2. Theo shard/partition/table/collection

Bổ sung:

- Top N largest partitions/collections.
- Top N fastest-growing shards.
- Hot partitions theo IOPS/QPS.
- Uneven disk usage giữa replicas.
- Compaction debt theo table/range khi có metrics.
- Index size và index usage.
- Tenant data footprint khi được phép đo.

### 9.3. Theo failure domain

Nếu các replicas thuộc cùng AZ hoặc volume group, một sự cố có thể làm nhiều nodes mất đồng thời. Capacity cho recovery phải tính **node/zone bị mất**, không chỉ trạng thái khỏe mạnh.

### 9.4. Một node mới chưa chắc giúp ngay

Thêm node thường cần bootstrap, shard relocation, data streaming, query routing thay đổi và có thể compaction. Khi volume gần đầy, **rebalancing chính nó tiêu thụ disk/network**.

### 9.5. High-cardinality caution

Gắn `tenant_id`, `document_id`, `partition_key` không giới hạn vào Prometheus labels có thể làm hệ monitoring quá tải. Dùng bounded tenant cohorts, top-K reports, log sampling hoặc offline analytics cho keys cực lớn.

---

## 10. Disk IOPS, throughput và latency: ba phép đo riêng

### 10.1. IOPS

IOPS = số operations đọc/ghi trên giây, thường tách:

\[
IOPS_{\text{read}},\quad IOPS_{\text{write}}.
\]

Nó không phản ánh tổng bytes nếu kích thước request khác nhau.

### 10.2. Throughput

Băng thông:

\[
B_{\text{read/write}}
=\frac{\text{Bytes transferred}}{\text{Second}}
\]

đơn vị MiB/s hoặc MB/s; đừng lẫn MiB (2^20 bytes) và MB (10^6 bytes).

### 10.3. Average I/O size

\[
S_{\text{avg}}\approx
\frac{B_{\text{bytes/s}}}{IOPS}
\]

với IOPS lớn hơn 0. Nếu device ghi 100 MiB/s ở 25.600 IOPS:

\[
S_{\text{avg}}\approx4\text{ KiB/operation}.
\]

### 10.4. Latency

Disk latency có thể được phân tích theo device, OS block layer và database operation. **API p99 không phải disk p99**: nó còn gồm queueing, serialization, network, locks, replication và retries.

### 10.5. Queue depth

Số I/O requests đang chờ/đang xử lý. Queue tăng cùng latency có thể báo saturation; nhưng thiết bị NVMe có nhiều queues và concurrency, nên không dùng một ngưỡng queue cố định cho mọi device.

---

## 11. Đọc busy time và `%util` đúng cách

Trên Linux, công cụ như `iostat -x` cung cấp các trường thường gặp:

~~~text
r/s    w/s
rkB/s  wkB/s
r_await w_await
aqu-sz
%util
```

Tên trường/cách tính thay đổi theo phiên bản `sysstat` và kernel.

### 11.1. `%util` cao nghĩa gì?

Nó thường đại diện mức thời gian có I/O hoạt động theo cách kernel báo cáo. Trên một thiết bị serial, gần 100% có thể là tín hiệu bão hòa mạnh. Nhưng với SSD/NVMe hỗ trợ nhiều I/O song song, `%util` không phải một phép đo trực tiếp “đã dùng 100% maximum throughput”.

### 11.2. `await` cũng cần ngữ cảnh

`r_await`, `w_await` thường bao gồm thời gian từ lúc request đi qua những pha queue/service theo công cụ. Tăng có thể do queueing, device service chậm hoặc host throttling.

### 11.3. Volume/cloud storage có quotas khác

Một volume cloud có thể bị giới hạn:

- Provisioned IOPS.
- Provisioned throughput.
- Burst credits.
- Instance-level storage bandwidth.
- Queue depth/burst windows.
- Multi-tenant device contention.

Không suy từ spec SSD vật lý trên mạng về khả năng của volume ảo.

### 11.4. Sản lượng hoàn tất khác lưu lượng yêu cầu

Khi IOPS capped, throughput đo được có thể **đứng yên** dù application gửi thêm requests; queue/p99/timeout tăng mới là tín hiệu tải vượt capacity.

---

## 12. Little's Law để hiểu số I/O đang chờ

Trong trạng thái ổn định:

\[
L=\lambda W,
\]

với:

- \(L\): số công việc trung bình đang ở trong hệ.
- \(\lambda\): throughput được xử lý/giây.
- \(W\): thời gian trung bình của một công việc.

Ví dụ một storage path xử lý ổn định 10.000 I/O/s, latency trung bình 2 ms:

\[
L=10\,000\times0.002=20.
\]

Nếu latency tăng lên 20 ms mà throughput vẫn giữ 10.000/s:

\[
L=10\,000\times0.02=200.
\]

### 12.1. Giả định quan trọng

Công thức mô tả **steady state** với population/boundary nhất quán. Nếu request arrival tăng liên tục và hàng đợi không ổn định, không dùng công thức để kết luận hệ sẽ tự phục hồi.

### 12.2. Mục đích thực tế

So queue/in-flight với latency và throughput, tìm điểm khi tăng concurrency **không còn tăng goodput** mà chỉ tăng chờ đợi.

### 12.3. Client concurrency không là device queue depth

Một request NoSQL có thể tạo nhiều disk I/Os, chạm cache hoặc fan-out tới replicas; không suy mỗi HTTP request tương ứng đúng một device I/O.

---

## 13. Disk saturation có thể đến trước disk full

Một volume chỉ 40% used vẫn có thể chịu write stalls nếu ứng dụng tạo quá nhiều random writes hoặc một index build quét toàn dữ liệu.

### 13.1. Dấu hiệu saturation

- Throughput/IOPS chạm quota đã biết.
- Latency tăng nhanh khi load thêm.
- Queue depth tăng.
- Database compaction/flush backlog tăng.
- Read p99 và write p99 cùng xấu.
- I/O throttling/credits exhausted.
- Requests timeout/retry.

### 13.2. Dấu hiệu space pressure

- Filesystem available giảm.
- Per-node disk watermark vượt.
- Compaction không đủ temporary space.
- Index build/backup thất bại.
- Database chuyển read-only hoặc từ chối writes theo engine.
- Oplog/WAL cleanup không chạy được.

### 13.3. Hai vấn đề có thể cộng hưởng

Disk gần đầy khiến engine khó compact/rewrite, backlog tăng; backlog lại tạo I/O, làm request chậm; retries tăng tải. Vì vậy một incident có thể bắt đầu là capacity rồi trở thành performance outage.

### 13.4. Đừng tăng client retries để xử lý disk bottleneck

Nếu backend đang throttled, retry không giới hạn có thể nhân số attempts, tăng queue và kéo dài sự cố. Cần bounded retries, backoff/jitter và load shedding.

---

## 14. Foreground vs background I/O

Foreground:

- Point reads/writes.
- Conditional updates/CAS.
- Queries, scans.
- Transaction commit.
- Index lookups.

Background:

- LSM compaction/flush.
- TTL expiration và tombstone cleanup.
- Checkpoint, snapshot/backup.
- Replication catch-up và repair.
- Shard relocation/rebalance.
- Index build/backfill.
- Log/AOF rewrite.
- CDC replay/export.
- Search segment merge.

### 14.1. Khi dùng chung disk

~~~text
Foreground writes ----+
                      +--> disk / device quota
Compaction ----------+
Backup snapshot -----+
Repair --------------+
~~~

Một workload chỉ tạo 50 MiB/s foreground writes có thể vẫn quá tải disk quota 100 MiB/s nếu compaction ghi 50 MiB/s và backup đọc/ghi thêm 30 MiB/s.

### 14.2. Đừng tắt maintenance tùy tiện

Giảm compaction có thể làm p99 tốt tạm thời, nhưng pending bytes và disk usage tăng. Một hệ không xử lý kịp nợ maintenance cuối cùng sẽ stall hoặc đầy đĩa.

### 14.3. Cần quan sát cả quá trình phục hồi

Sau peak write, đo:

- Thời gian compaction backlog drain.
- Thời gian TTL cleanup bắt kịp.
- Thời gian disk usage về stable range.
- Thời gian replica lag hồi phục.
- Thời gian p99 trở về baseline.

---

## 15. LSM compaction: vì sao ổ đĩa đột ngột tăng

Một LSM engine có thể giữ input SSTables cho tới khi output compaction được ghi và metadata cập nhật an toàn.

~~~text
Before compaction:
  SSTable A: 100 GiB
  SSTable B:  80 GiB

During compaction:
  A + B still present
  New output C: up to ~160 GiB
  Temporary footprint can be large

After successful switch/cleanup:
  A and B become obsolete
  C remains
~~~

Số bytes minh họa, không là dự đoán chính xác cho mọi strategy.

### 15.1. Headroom là yêu cầu vận hành

Nếu chỉ còn 50 GiB available, một compaction cần viết 160 GiB output có thể thất bại hoặc không thể chạy.

### 15.2. Compaction debt

Một hệ ghi dữ liệu nhanh hơn khả năng compaction lâu dài có thể thấy:

~~~text
pending_compaction_bytes ↑
disk_used_bytes ↑
read_amplification ↑
write_stalls ↑
~~~

Số liệu pending bytes phụ thuộc engine, không phải mọi hệ đều expose giống nhau.

### 15.3. Dung lượng tạm và tốc độ tăng có thời điểm

Không chỉ dự báo trung bình GiB/ngày. Một maintenance batch có thể tạo **peak instantaneous space requirement** lớn. Capacity plan cần một khoản **temporary headroom** riêng.

---

## 16. Cassandra: điều gì nên đo?

Apache Cassandra sử dụng memtable/commit log/SSTable và compaction. Những nhóm số liệu hữu ích:

- Per-node filesystem used/available.
- Keyspace/table live disk space used.
- SSTables count/size.
- Total disk space used của table, snapshots.
- Compaction pending tasks/bytes/time.
- Flush pending/blocked operations.
- Tombstone scans và read latency.
- Commit log usage.
- Repair/streaming progress.
- Read/write latency, timeouts.
- Node/partition ownership và data distribution.
- JVM heap/GC pauses, CPU/network.

### 16.1. Phân biệt live và total disk space used

Các Cassandra metrics/`nodetool tablestats` có thể cung cấp live SSTable bytes và total bytes tính thêm những thứ phù hợp với phiên bản/metric. Không cộng các trường này một cách mù quáng hoặc coi chúng bằng filesystem used.

### 16.2. Công cụ gợi ý

~~~text
nodetool tablestats
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool status
~~~

Các lệnh là điểm bắt đầu chẩn đoán. Tên field, JMX metrics và quyền truy cập tùy bản Cassandra; hạn chế thao tác mang tính thay đổi trên production nếu không có runbook.

### 16.3. STCS/LCS/TWCS

Strategy ảnh hưởng write/read/space amplification và thời điểm reclaimed SSTables. Một workload TTL theo time buckets có thể hợp TWCS khi timestamps/retention/late writes phù hợp; dữ liệu hỗn hợp có thể không.

### 16.4. Tombstone nhiều, disk không giảm

DELETE/TTL có thể tạo tombstones, cần chờ điều kiện GC và compaction. Không giảm `gc_grace_seconds` vội để thu hồi disk: offline replica chưa repair có thể tạo zombie data khi quay lại.

### 16.5. Disk skew trong cluster

RF=3 không bảo đảm mỗi node chiếm chính xác cùng bytes. Token ranges, partition sizes, vnode distribution, hot tenants, snapshots và repair ảnh hưởng. Theo dõi **worst node**, không chỉ tổng cluster.

### 16.6. Khi gần đầy

Trước khi thêm node/cấu hình compaction, phải kiểm disk headroom cho bootstrap/rebalance, khả năng repair, snapshot cleanup được phép và nguy cơ compaction pressure. Tuyệt đối không xóa SSTable/commit log bằng thao tác file thủ công để “giải phóng nhanh”.

---

## 17. MongoDB: data size, storage size và index size

MongoDB với WiredTiger thường cần xem:

- `dataSize`: lượng dữ liệu logic theo thống kê được báo cáo.
- `storageSize`: storage allocated cho collection theo định nghĩa metric.
- `totalIndexSize`: kích thước indexes.
- Storage/free space details nếu phiên bản hỗ trợ.
- Disk filesystem used/available.
- WiredTiger cache dirty/eviction metrics.
- Checkpoint activity.
- TTL deletions.
- Oplog usage/window.
- Replication lag.
- Sharding chunk migrations/balancer.
- Query/command latency và disk metrics ở OS/cloud.

### 17.1. Ví dụ lệnh quan sát

~~~javascript
db.stats()
db.orders.stats()
db.serverStatus().wiredTiger
db.serverStatus().metrics
~~~

Với các triển khai/phát hành khác nhau, API statistics và field naming có thể thay đổi hoặc có replacement commands. Dùng tài liệu đúng MongoDB version và quyền phù hợp.

### 17.2. `dataSize` thấp nhưng `storageSize` cao

Có thể do:

- Cấu trúc allocated/page reuse.
- Dữ liệu đã delete nhưng chưa trả physical storage.
- Fragmentation.
- Compression/page overhead.
- Indexes hoặc metadata nếu so số liệu không cùng scope.

Không tự kết luận có dữ liệu bị nhân bản khi chưa kiểm.

### 17.3. WiredTiger space reuse

MongoDB có thể tái sử dụng free space bên trong data files; file trên filesystem không nhất thiết co ngay khi DELETE chạy. `compact` (nơi được hỗ trợ) là thao tác riêng, có ảnh hưởng tới I/O và availability; không sử dụng như routine đầu tiên khi p99 cao.

### 17.4. TTL index

Một TTL monitor chạy nền có thể xóa documents bất đồng bộ. Một đợt document cùng `expiresAt` có thể tạo delete/index/oplog load lớn, gây spike disk I/O.

### 17.5. Sharding

Bổ sung dashboard theo **shard**, không chỉ mongos hoặc aggregate cluster: một shard có thể chứa tenant/hot range lớn. Rebalancing có thể làm disk/network tăng trong thời gian chuyển chunks/ranges.

---

## 18. DynamoDB: không có `df -h` cho khách hàng

Amazon DynamoDB là managed NoSQL service: bạn không có quyền đo host disk used/available và SSTable compaction như một cluster Cassandra tự vận hành.

Những số liệu/công cụ có ích:

- Table/item count và table size statistics khi dịch vụ cung cấp.
- GSI size và GSI write/read capacity.
- Consumed read/write capacity units.
- Provisioned/on-demand capacity behavior.
- Throttling và unsuccessful requests.
- Client-side latency/retries.
- Hot partition/key distribution theo insight phù hợp.
- TTL deleted item metrics khi khả dụng.
- Backup/export/PITR/quota/cost.

### 18.1. Table size statistics không phải real-time gauge mọi giây

Một số kích thước hoặc item-count statistics được làm mới theo chu kỳ dịch vụ, nên không dùng chúng như alert duy nhất cho burst tăng trong phút. Kết hợp write rate, item size sampling và quota/cost metrics.

### 18.2. GSI có footprint riêng

Mỗi GSI lưu một projection của indexed attributes; thêm GSI có thể tạo backfill và tăng storage/write cost. Index thiết kế không phù hợp cũng có thể tạo hot partition dù table source phân phối tốt.

### 18.3. Capacity throttling không đồng nghĩa disk full

Một DynamoDB request bị throttle có thể vì key distribution hoặc capacity service/index, không phải “đĩa AWS đầy”. Không khẳng định nguyên nhân storage nội bộ khi không có telemetry tương ứng.

### 18.4. TTL deletion không chính xác từng giây

Expired item có thể còn tồn tại một khoảng thời gian trước khi cleanup. Business logic cần kiểm `expiresAt` theo yêu cầu, không chỉ phụ thuộc physical deletion.

### 18.5. Capacity plan theo đơn vị dịch vụ

Đối với DynamoDB, nên lập kế hoạch theo **data/index storage, RCU/WCU hoặc request quota, hot-key limits, backup cost, TTL lag và growth**, thay vì cố mô phỏng disk headroom của self-hosted LSM.

---

## 19. Redis: memory capacity là chính, disk là persistence

Redis cache/in-memory database cần tách:

- `used_memory`: logical allocator-used memory theo engine.
- RSS/memory fragmentation.
- `maxmemory` và eviction policy.
- Key count và expiry rate.
- RDB snapshot size.
- AOF size/rewrite growth.
- Persistence disk free.
- Copy-on-write memory khi fork/rewrite.
- Replication buffers.
- Latency/slowlog.

### 19.1. Bộ nhớ đầy trước disk

Một Redis cache có thể bắt đầu eviction hoặc từ chối writes theo policy dù disk filesystem còn rất nhiều dung lượng. Đừng đặt alert “Redis full” chỉ bằng `node_filesystem_avail_bytes`.

### 19.2. AOF tăng trưởng

AOF chứa các write operations và có thể tăng cho đến khi rewrite/cleanup theo cấu hình. Khối lượng AOF writes có thể cao dù live keys không tăng.

### 19.3. RDB snapshots

`BGSAVE` và rewrite có thể tạo temporary disk I/O, CPU/fork/CoW memory. Storage headroom cho persistence khác memory headroom cho cache values.

### 19.4. Thông số tham khảo

~~~text
INFO memory
INFO persistence
INFO stats
INFO replication
LATENCY LATEST
SLOWLOG GET
~~~

Các trường có thể thay đổi theo Redis version/service tier. `SLOWLOG` không phản ánh toàn bộ network/client queue latency.

### 19.5. Mất cache không phải lúc nào là mất nguồn nghiệp vụ

Nếu Redis chỉ lưu derived cache, disk/memory sizing còn cần xét cold-miss amplification lên NoSQL source. Nếu Redis giữ session/idempotency/queue state duy nhất, durability và backup phải được xét như một thành phần nghiêm túc hơn cache thông thường.

---

## 20. RocksDB: pending compaction, stalls và levels

RocksDB là embedded LSM engine. Các nhóm metric/property thường gặp (tùy phiên bản):

~~~text
rocksdb.estimate-pending-compaction-bytes
rocksdb.num-running-compactions
rocksdb.num-immutable-mem-table
rocksdb.cur-size-all-mem-tables
rocksdb.levelstats
rocksdb.stats
rocksdb.num-files-at-level<N>
~~~

### 20.1. Pending compaction bytes

Giúp ước lượng backlog cần xử lý trong engine. Nếu tăng liên tục khi workload ổn định, sustained compaction throughput có thể không theo kịp.

### 20.2. Write stalls

Nếu L0/files/memtables quá nhiều, engine có thể slowdown hoặc stop writes để giữ hệ an toàn. Khi đó client p99 xấu có thể là dấu hiệu **debt**, không phải do mạng.

### 20.3. Level distribution

Quan sát files/bytes theo level, block cache hit ratio và compaction read/write bytes; từ đó đánh giá read vs write amplification.

### 20.4. Snapshots và iterators

Long-lived snapshots/iterators có thể giữ old versions/files và trì hoãn reclaim trong một số trường hợp. Rà soát lifecycle của embedded engine trước khi kết luận “compaction không xóa được dữ liệu”.

### 20.5. Embedded không có nghĩa miễn phí

Nếu một Java service dùng RocksDB nội bộ (ví dụ state store), disk I/O cùng máy có thể tranh với application threads và OS page cache. Đặt storage capacity/headroom cho **từng instance** thay vì chỉ xem external database.

---

## 21. Elasticsearch/OpenSearch: segment và disk watermarks

Lucene-based search engines dùng segments; updates/deletes không nhất thiết trả disk bytes ngay. Segment merge giải phóng/organize space về sau.

Theo dõi:

- Primary store size vs total store size bao gồm replicas.
- Segments count/size.
- Deleted docs.
- Merge time/bytes/current merges.
- Indexing/refresh/flush/translog.
- Filesystem per node.
- Shard relocation/recovery.
- JVM heap/GC và page cache.
- Disk watermarks / allocation decisions.

### 21.1. Primary vs replicated size

Khi xem `_cat/indices`, size của primary data khác tổng store size của toàn replicas. Không nhân RF lần nữa nếu metric đã chứa replica bytes.

### 21.2. Một node đầy gây phân bổ shards bất thường

Disk watermarks có thể ảnh hưởng shard allocation và write behavior theo phiên bản/cấu hình. Cluster average còn trống không ngăn một node chạm high/flood-stage watermark.

### 21.3. Segment merges cần temporary space

Force merge có thể tạo substantial extra I/O và temporary bytes. Không ép force merge mọi write-heavy indices chỉ để thấy disk giảm ngắn hạn.

### 21.4. API quan sát khái quát

~~~text
GET /_cat/allocation?v
GET /_cat/indices?v
GET /_cat/segments?v
GET /_nodes/stats/fs,indices
GET /_stats/store,merge
~~~

Tùy Elasticsearch/OpenSearch version, endpoints và field path có thể khác. Không quét toàn cluster bằng các lệnh nặng quá thường xuyên chỉ để làm dashboard.

### 21.5. Retention theo index/rollover

Time-based indices/data streams có thể giúp xóa theo từng index thay vì hàng triệu document deletes, nếu access pattern và retention policy cho phép. Nhưng cần kế hoạch shard count, rollover, snapshot và legal hold.

---

## 22. Couchbase: disk fragmentation, index và replication

Một Couchbase deployment có thể có:

- Data bucket/item storage size.
- Data disk usage và fragmentation.
- Index disk/storage separately.
- Expiry/deletion/compaction.
- DCP/replication backlog.
- Replica copies.
- XDCR traffic trong cross-region.
- Backup, rebalance và failover.

### 22.1. Data service vs index service

Một bảng tổng bucket không nhất thiết phản ánh index disk ở node/service khác. Đặt alerts theo từng service/resource.

### 22.2. Auto-compaction

Cấu hình/thresholds phù hợp theo phiên bản giúp thu hồi hoặc reorganize storage; công việc này có thể tranh I/O với foreground KV operations.

### 22.3. Rebalance có thể tiêu thụ disk tạm

Thêm node hoặc failover dẫn đến data movement và replication. Dung lượng mới không tự phân bổ lại lập tức.

### 22.4. Expiry và purge semantics

Dữ liệu expired/deleted có thể còn tombstone/purge metadata trong thời gian cần cho replication/stream. Không giảm purge retention tùy tiện nếu có offline replicas hoặc consumers.

---

## 23. Log retention, snapshot và backup: nguồn tăng trưởng thường bị bỏ qua

Một node có thể chứa:

~~~text
/data/
  db-data/
  indexes/
  wal/
  snapshots/
  temporary-compaction/
  cdc/
  diagnostics/
  backups/
~~~

Không phải engine nào bố trí như vậy; đây là sơ đồ minh họa để kiểm nguyên nhân `df` tăng.

### 23.1. WAL/oplog/commit log

Retention có thể phụ thuộc backup, replication lag, consumer checkpoint hoặc cấu hình recovery. Nếu một replica/CDC consumer chậm, source log có thể phải giữ lâu hơn, làm disk tăng.

### 23.2. Snapshots và hard links

Một snapshot có thể dùng hard links/Copy-on-Write, nên kích thước báo cáo của thư mục không bằng bytes thêm vào filesystem. Công cụ cộng dung lượng từng file có thể double-count shared blocks.

### 23.3. Incremental backups

Incremental backup có thể tiết kiệm dung lượng nhưng retention chain và restore points phải được quản lý. Không xóa một phần chain tùy ý chỉ để giải phóng disk.

### 23.4. Backup trên cùng failure domain

Một bản backup nằm cùng volume/cụm có thể dùng disk nhưng không giúp khi volume mất hoàn toàn. Cần mục tiêu DR, vị trí lưu và restore drill.

### 23.5. Logs diagnostic có cardinality cao

Một ứng dụng log toàn bộ JSON payload mỗi request có thể tạo nhiều disk bytes hơn chính dataset nếu lưu local quá lâu. Tách log/trace budgets và không log dữ liệu nhạy cảm không cần thiết.

---

## 24. Phân biệt “disk full thật” với số liệu nhìn mâu thuẫn

### 24.1. `df` cao nhưng `du` thấp

Có thể có:

- Files đã unlink nhưng process còn mở.
- Filesystem reserved space.
- Mount/overlay/snapshot behavior.
- Quota khác nhau.
- Hidden directories hoặc quyền không đọc được.
- Tệp ở filesystem khác khi kiểm bằng path không đúng.

### 24.2. Database báo ít data nhưng OS disk lớn

Kiểm snapshots, WAL, indexes, backups, temporary files, logs và other services. Đừng xóa file chỉ dựa vào extension.

### 24.3. OS disk rảnh nhưng database báo near-full

Có thể là per-table quota, disk watermark, partition-level quota, managed storage quota, maxmemory hoặc service config.

### 24.4. Tăng trưởng âm đột biến

Có thể do:

- Compaction cleanup.
- Snapshot rotation.
- Delete retention/index drop.
- Node replacement và metrics label đổi.
- Mountpoint thay đổi.
- Monitoring thiếu series.

Xem sự kiện vận hành trước khi giải thích đó là business data shrink.

### 24.5. Counters reset

IO byte counters có thể reset khi node restart. Khi tính rates, cần dùng `rate()`/counter semantics phù hợp thay vì `delta()` tùy tiện trên counters.

---

## 25. Thu thập dữ liệu ở ba lớp

### Lớp 1 — Ứng dụng Java

- Logical read/write/delete operations/s.
- Payload/serialized bytes.
- End-to-end request latency.
- Attempts/retries/timeouts.
- API error rate.
- Tenant/workload class.
- Batch/export/CDC job volume.

### Lớp 2 — Database server/service

- Logical/physical database size.
- Index/table/shard sizes.
- SSTables/segments and compaction backlog.
- TTL/delete/eviction metrics.
- Internal queue/connection wait.
- Replication/repair/backup/index build status.
- Query/command p99.
- Service throttling/quota.

### Lớp 3 — Host/device/cloud volume

- Filesystem used/available/total.
- Volume IOPS and bytes/s.
- I/O wait/latency/queue.
- Device busy time and quota/credits.
- CPU/memory/OS page cache.
- Network I/O.
- Hardware errors/filesystem alerts.

### 25.1. Tránh nhầm ranh giới

Một metric `disk_write_bytes_total` đo host device có thể bao gồm OS logs và dịch vụ khác. Một metric `database_storage_bytes` có thể đã gồm replicas. Không dùng hai metric không cùng scope để tính WA mà không ghi giả định.

### 25.2. Correlate trên cùng thời gian

Clock skew, scrape interval, exporter restart và dashboard downsampling có thể làm timeline lệch. Cần timestamp alignment trước khi khẳng định compaction gây một latency spike.

---

## 26. Prometheus/Node Exporter: những truy vấn minh họa

Ví dụ sau giả định Linux hosts có `node_exporter`. Tên metric và labels là ví dụ phổ biến, cần xác nhận chính xác exporter/runtime đang triển khai.

### 26.1. Used percent theo filesystem

~~~promql
100 *
(
  1 -
  node_filesystem_avail_bytes{
    fstype!~"tmpfs|overlay"
  }
  /
  node_filesystem_size_bytes{
    fstype!~"tmpfs|overlay"
  }
)
~~~

`avail_bytes` là dung lượng sẵn có cho user-space theo filesystem; dùng `size` làm mẫu số cho biết tỷ lệ **không còn available**. Nó không nhất thiết bằng tỷ lệ physical blocks allocated do reserved blocks/quota. Lọc đúng mountpoint/device để không đếm root/container overlay nhiều lần.

### 26.2. Available GiB theo node/mount

~~~promql
node_filesystem_avail_bytes{
  mountpoint="/var/lib/nosql"
} / 1024^3
~~~

### 26.3. Disk read/write MiB/s

~~~promql
sum by (instance, device) (
  rate(node_disk_read_bytes_total[5m])
) / 1024^2
~~~

~~~promql
sum by (instance, device) (
  rate(node_disk_written_bytes_total[5m])
) / 1024^2
~~~

### 26.4. Read/write IOPS

~~~promql
sum by (instance, device) (
  rate(node_disk_reads_completed_total[5m])
)
~~~

~~~promql
sum by (instance, device) (
  rate(node_disk_writes_completed_total[5m])
)
~~~

### 26.5. Average disk I/O latency

Một ví dụ average read duration trên block-layer counter:

~~~promql
rate(node_disk_read_time_seconds_total[5m])
/
clamp_min(
  rate(node_disk_reads_completed_total[5m]),
  1e-9
)
~~~

Đơn vị là **seconds/read**, có thể nhân 1000 để hiển thị ms/read. Phép tính đo **trung bình**, không phải p99; metrics tầng host không tự có histogram p99 cho từng read. Khi IOPS thấp, sample không ổn định.

### 26.6. I/O busy fraction

~~~promql
rate(node_disk_io_time_seconds_total[5m])
~~~

Kết quả hướng tới tỉ lệ thời gian có I/O activity theo kernel counter, **không là phần trăm capacity tối đa đáng tin trên mọi NVMe/cloud volume**. Cần kết hợp throttling/latency/queue.

### 26.7. Cẩn trọng với device labels

Một logical request có thể đi qua filesystem → LVM/RAID → virtual device → underlying disks. Cộng tất cả device counters có thể double-count cùng I/O ở nhiều tầng. Dashboard phải chọn **một tầng block device rõ ràng** để giải thích.

---

## 27. PromQL dự báo tăng trưởng: dùng để cảnh báo, không coi là lời tiên tri

Giả sử có gauge:

~~~text
nosql_node_physical_bytes{node="db-01"}
```

### 27.1. Growth GiB/day theo độ dốc

~~~promql
deriv(
  nosql_node_physical_bytes{node="db-01"}[7d]
) * 86400 / 1024^3
~~~

`deriv()` tính slope tuyến tính ước lượng trên gauge. Với compaction/snapshot tạo sawtooth, slope nhạy với cửa sổ; cần xem nhiều horizons.

### 27.2. Phép dự báo đơn giản

Có thể so `predict_linear(metric[7d], 7*24*3600)` với một threshold bytes, **nhưng** đây là linear extrapolation. Khi data retention, index migration hoặc node rebalancing thay đổi, forecast có thể sai mạnh.

### 27.3. Không cộng gauges rồi mới suy theo instance vô thức

Nếu `nosql_node_physical_bytes` có label replica/volume, phải xác định data đã được đếm ở mỗi node. Forecast cần **per-node worst case**, không chỉ sum cluster.

### 27.4. Độ tin cậy của forecast

Dùng kèm:

- Forecast 7d/30d.
- Growth 1d/7d/30d.
- Peak daily increase.
- Scheduled one-time jobs.
- Confidence/bounds khi có mô hình phù hợp.
- Human review trước thay đổi storage lớn.

---

## 28. Đặt ngưỡng cảnh báo ba tầng

Một dashboard có thể có:

| Mức | Tình huống | Phản ứng đề xuất |
|---|---|---|
| **Watch** | Growth nhanh, 30 ngày tới ngưỡng policy | Capacity review, xác minh forecast |
| **Warning** | Một node sắp chạm ngưỡng trong 14 ngày | Lên lịch mở rộng/cleanup an toàn |
| **Critical** | Free/headroom thấp hơn temporary compaction requirement hoặc ETA vài ngày | Giảm tải và thực hiện runbook |
| **Immediate** | Write failures, read-only, disk full/throttle nghiêm trọng | Incident response bảo vệ dữ liệu |

Mức ngày và phần trăm chỉ là **ví dụ**. Thiết kế alert theo thời gian mua/provision thêm capacity, dữ liệu có tính mùa vụ và mức đe dọa tới business.

### 28.1. Thời gian hành động quan trọng hơn phần trăm

Nếu mở rộng cluster cần 5 ngày, alert trước 2 ngày là quá muộn. Ngược lại, alert disk 80% nhưng data sẽ tự expire vào ngày mai có thể cần điều tra thay vì tăng volume ngay.

### 28.2. Dùng `for` để tránh nhiễu

Prometheus alert rule thường có thể yêu cầu điều kiện giữ vài phút nhằm giảm false positives, nhưng đối với disk full đột ngột không nên đợi quá lâu.

### 28.3. Alerts theo worst node/shard

Một warning cluster-average là chưa đủ. Có thể cần `max by (cluster)(used_percent)`, hoặc alert trực tiếp theo node/mount.

### 28.4. Alert p99 cùng compaction debt

Nếu disk sử dụng 78% nhưng p99 ổn định và pending work về 0, mức khẩn có thể khác node 78% với pending compaction tăng vô hạn, stalled writes và disk I/O throttling.

---

## 29. Giám sát capacity khi scale và failover

### 29.1. Scale-out không miễn phí

Thêm node:

1. Cần cấp volume/instance.
2. Chờ bootstrap/rebalance.
3. Source nodes phải stream data.
4. Destinations cần temporary disk.
5. Indexes/compaction có thể tăng.
6. Traffic/routing bắt đầu chuyển.
7. Phải kiểm dữ liệu đã đủ replicas/quorum theo design.

### 29.2. Failover làm skew tăng

Nếu một node/AZ mất, các replicas/nodes còn lại có thể nhận thêm read/write load và data movement. Capacity N+1/N+AZ cần đánh giá riêng.

### 29.3. Không chỉ kiểm cluster free sau thêm node

Node mới có thể còn trống nhưng nodes cũ vẫn nguy hiểm trong nhiều giờ. Cần nhìn per-node headroom **trong quá trình** streaming.

### 29.4. Vertical scale

Tăng volume size có thể nhanh hơn thêm node trong một số dịch vụ, nhưng không phải luôn tăng IOPS/throughput tương ứng. Cloud disk quotas có thể tách capacity vs provisioned performance.

### 29.5. Tiered storage

Một số hệ dùng object storage/remote tiers cho dữ liệu lạnh. Hãy đo riêng local hot storage, remote bytes, object count, network egress, cache miss và restore latency; đừng cộng thành một con số free space.

---

## 30. Java Micrometer: đo kích thước payload và latency logic

Ví dụ Java 17 tạo một wrapper cho repository. Đây là **đo từ phía ứng dụng**, không phải sensor đo disk physical I/O.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Objects;
import java.util.function.Supplier;

public final class NoSqlClientMetrics {

    private final MeterRegistry registry;

    public NoSqlClientMetrics(MeterRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public <T> T observeWrite(
            String operationClass,
            long serializedBytes,
            Supplier<T> call) {

        if (serializedBytes < 0) {
            throw new IllegalArgumentException(
                "serializedBytes cannot be negative"
            );
        }

        String kind = boundedKind(operationClass);

        DistributionSummary.builder(
                "nosql.client.payload.bytes")
            .baseUnit("bytes")
            .tag("operation", kind)
            .register(registry)
            .record(serializedBytes);

        Timer timer = Timer.builder(
                "nosql.client.operation.latency")
            .tag("operation", kind)
            .register(registry);

        try {
            T result = timer.record(call);

            Counter.builder("nosql.client.operations")
                .tag("operation", kind)
                .tag("result", "success")
                .register(registry)
                .increment();

            return result;
        } catch (RuntimeException | Error failure) {
            Counter.builder("nosql.client.operations")
                .tag("operation", kind)
                .tag("result", "failure")
                .register(registry)
                .increment();

            throw failure;
        }
    }

    private static String boundedKind(String operation) {
        return switch (operation) {
            case "point_write" -> "point_write";
            case "batch_write" -> "batch_write";
            case "delete" -> "delete";
            default -> "other";
        };
    }
}
~~~

### 30.1. Đo bytes đúng scope

`serializedBytes` nên là kích thước representation được chọn (ví dụ BSON/Protocol payload) và nhất quán giữa samples. Nó **không** bằng physical disk bytes vì compression, WAL, indexes, replicas và compaction.

### 30.2. Không dùng document ID làm metric label

Labels như `user_id`, `order_id` hoặc `partition_key` tùy ý tạo cardinality lớn, tăng chi phí memory của metrics server. Các nhóm label cố định như `operation`, `db_type`, `result` phù hợp hơn.

### 30.3. Phân loại latency

Đo được method call latency; nếu driver retry bên trong, một logical call có thể gồm nhiều attempts. Muốn tách attempts phải dùng driver instrumentation phù hợp.

### 30.4. Async không được đo tại thời điểm trả Future

Nếu `call()` chỉ tạo `CompletionStage`, `Timer.record()` bao quanh hàm đó sẽ kết thúc trước khi DB trả kết quả. Cần thời gian từ lúc bắt đầu đến khi stage hoàn tất.

---

## 31. Java: đo async completion đúng cách

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.Objects;
import java.util.concurrent.CompletionStage;
import java.util.function.Supplier;

public final class AsyncDbMetrics {

    private final MeterRegistry registry;

    public AsyncDbMetrics(MeterRegistry registry) {
        this.registry = Objects.requireNonNull(registry);
    }

    public <T> CompletionStage<T> time(
            String operationClass,
            Supplier<CompletionStage<T>> supplier) {

        Timer timer = Timer.builder(
                "nosql.client.async.latency")
            .tag("operation", operationClass)
            .register(registry);

        Timer.Sample sample = Timer.start(registry);

        try {
            CompletionStage<T> stage =
                Objects.requireNonNull(supplier.get());

            return stage.whenComplete(
                (result, error) -> sample.stop(timer)
            );
        } catch (RuntimeException | Error failure) {
            sample.stop(timer);
            throw failure;
        }
    }
}
~~~

### 31.1. Khi Future bị timeout local

Nếu SDK/client hoàn tất Future do timeout nhưng request server vẫn chạy, metric là **caller-observed latency**, không là disk execution time thực. Correlate với server metrics và attempt IDs nếu cần.

### 31.2. Reactive pipelines

Với `Mono`/`Flux`, bắt đầu đo ở **subscription** khi source cold; dừng khi complete/error/cancel theo contract. Không đo thời gian tạo một Publisher rồi kết luận DB đã query.

### 31.3. Thêm histograms có kiểm soát

Micrometer có histogram/SLO bucket configuration theo backend; quá nhiều buckets × labels có thể tốn memory. Ghi `p99` cần biết histogram client/server được tính thế nào, không suy từ average.

### 31.4. Đặt monitor đủ nhẹ

Instrumentation không nên serialize lại payload vài lần chỉ để đo bytes, cũng không nên trace mọi data row lớn kèm PII.

---

## 32. Dashboard thiết kế theo ba tầng

### 32.1. Tầng tổng quan — điều hành

~~~text
Critical: Nodes below safe free-space headroom
ETA to threshold (worst node)
Logical data growth GiB/day
Physical storage growth GiB/day
Disk I/O latency p95/p99 (if available)
DB request p99 and error rate
Pending maintenance bytes/time
Current/forecast cost
~~~

### 32.2. Tầng chẩn đoán — SRE/DBA

~~~text
Per node/mount:
  total/available/used bytes
  read/write IOPS, MiB/s, io wait/queue
  pressure/throttle counters
  compaction/flush/TTL/repair progress

Per data scope:
  table/collection/index sizes
  active/expired/deleted records
  log/snapshot/backup bytes
  shard distribution
~~~

### 32.3. Tầng truy nguyên — incident

~~~text
Timeline:
  deployment changes
  traffic spikes
  batch/backfill start/stop
  index build
  compaction/TTL waves
  disk quota change
  replica failover
  node/zone maintenance
  backup/restore
~~~

### 32.4. Dashboard phải có đơn vị và phạm vi

Một ô ghi “Storage 3000” là vô nghĩa. Cần `GiB`, `per node`, `includes indexes?`, `replicas included?`, `scrape interval` và `source metric`.

### 32.5. Không chạy query quản trị nặng mỗi 5 giây

Một số stats per-partition/full collection scan tốn CPU/I/O. Dùng server-exported counters cho high-frequency, còn top-N partitions/index stats có thể thu thập định kỳ với budget.

---

## 33. Bảng dữ liệu mẫu để phân tích capacity

| Node | Usable GiB | Used GiB | Used % | Growth GiB/day | Days to 80% |
|---|---:|---:|---:|---:|---:|
| db-a | 2048 | 1500 | 73.2% | 20 | 6.9 |
| db-b | 2048 | 1100 | 53.7% | 35 | 15.4 |
| db-c | 2048 | 900 | 43.9% | 12 | 61.5 |
| db-d | 2048 | 1350 | 65.9% | 2 | 144.2 |

Cách tính với ngưỡng \(0.8\times2048=1638.4\) GiB:

- db-a: \((1638.4-1500)/20=6.92\) ngày.
- db-b: \((1638.4-1100)/35\approx15.38\) ngày.
- db-c: \((1638.4-900)/12\approx61.53\) ngày.
- db-d: \((1638.4-1350)/2=144.2\) ngày.

**db-a cần hành động sớm nhất**, mặc dù db-b có growth rate lớn hơn. Đây là dữ liệu minh họa, chưa cộng peak maintenance/failover headroom.

### 33.1. Nên ưu tiên forecast theo worst node

Nếu một node hết chỗ, nhiều hoạt động replication/index/compaction có thể thất bại dù cluster còn free space.

### 33.2. Phải cập nhật tốc độ sau rebalancing

Khi shard ownership đổi, growth rate per-node cũ có thể không còn có ý nghĩa. Theo dõi cả per-partition source growth để phân tích nguyên nhân nền.

---

## 34. Capacity review trước một thay đổi sản phẩm

Một sản phẩm muốn tăng retention từ 90 ngày lên 365 ngày và thêm hai secondary indexes.

### 34.1. Câu hỏi cần trả lời

- Ingest logical bytes/day là bao nhiêu?
- Nén thế nào theo dữ liệu thật?
- Old versions và TTL cleanup mất bao lâu?
- Replication copies và region count?
- Index footprint theo field/cardinality?
- Backfill peak disk và I/O?
- Có dual-write/dual-index trong rollout?
- Cần lưu WAL/oplog lâu hơn cho CDC?
- RPO/RTO và backup retention có thay?
- Khả năng node failure khi đang backfill?

### 34.2. Một mô hình giản lược

Giả sử 10 GiB compressed data/day, chưa tính index/replica:

- 90 ngày → ~900 GiB live.
- 365 ngày → ~3650 GiB live.

Chênh ~2750 GiB logical compressed data **trước replication/index overhead**. Nếu RF=3 và copies tương đương, riêng data replicated ước tính tăng 8250 GiB toàn cluster, chưa cộng index/backfill/temp.

### 34.3. Thay đổi retention là thay đổi cả capacity và performance

Dữ liệu nhiều hơn có thể làm index lớn, read range rộng, compaction/GC tốn tài nguyên và backups chậm hơn. Không chỉ tính phí storage.

---

## 35. Theo dõi top-N partitions/keys tăng nhanh

NoSQL thường partition/shard theo keys. Một partition quá lớn/hot có thể làm cả latency và disk skew tăng.

### 35.1. Các câu hỏi

- Top 10 partitions lớn nhất là gì?
- Partition nào tăng nhanh nhất 24 giờ?
- Có tenant mới gửi gấp 10 lần bình thường?
- TTL/cold data có tập trung vào một shard?
- Rebalance có chuyển được partition không?
- Partition size có vượt mục tiêu data model?

### 35.2. Theo engine

Cassandra có các công cụ/thống kê giúp phát hiện large partitions theo phiên bản; MongoDB sharding có chunk/range distribution; DynamoDB cung cấp insight giới hạn về hot keys/capacity theo dịch vụ; Redis có thể sampling big keys/memory usage.

**Không chạy full key scan/traversal đắt trên production** chỉ để biết top 10 nếu không được kiểm soát.

### 35.3. Tenant privacy

Top tenant size có thể là dữ liệu nhạy cảm về kinh doanh. Dashboard per-tenant cần access control và không làm lộ keys, emails hay payload.

### 35.4. Hot key khác large key

Một key nhỏ nhưng được đọc 1 triệu lần/giây có thể gây bottleneck, trong khi một partition rất lớn nhưng gần như không truy cập lại gây capacity risk. Theo dõi **size và access rate** riêng.

---

## 36. Dung lượng không tăng nhưng SSD vẫn bị quá tải

Một dataset giữ cố định 100 GiB nhưng được cập nhật toàn bộ mỗi giờ:

~~~text
Live data ~= 100 GiB
Updates per hour ~= 100 GiB logical writes
LSM compaction rewrites old data
Indexes updated
WAL / journal appended
~~~

Physical write volume rất lớn dù net disk growth gần 0.

### 36.1. Vì sao quan trọng với SSD

- Có IOPS/throughput limit.
- Có endurance/write-wear budget theo loại thiết bị.
- Compaction làm write amplification tăng.
- Backup/index rebuild cũng tranh bandwidth.
- Device latency thay đổi theo sustained workload.

### 36.2. Không dùng `disk_used` làm metric proxy của disk wear/load

Cần `bytes_written_total`, IOPS, latency, device health và engine compaction metrics.

### 36.3. Giá trị của write coalescing

Giảm số updates trùng/không cần thiết, batch hợp lệ và điều chỉnh model có thể giảm physical write workload nhiều hơn chỉ tăng dung lượng ổ.

---

## 37. Data lake, archive và tiering: lưu lâu nhưng không trên hot disk

Một chính sách có thể:

~~~text
0–7 ngày: hot NoSQL data
8–90 ngày: warm/secondary storage
>90 ngày: archive/object storage
~~~

### 37.1. Kiểm business query

Nếu app vẫn cần point lookup theo ID cho dữ liệu 2 năm tuổi, chuyển archive phải có retrieval path/SLA rõ. Đừng tiết kiệm disk rồi làm mất dữ liệu cần phục vụ.

### 37.2. CDC và deletion propagation

Nếu user xóa dữ liệu, archive và backups có thể cần xóa/ẩn theo policy. Tiering không được bỏ qua delete semantics.

### 37.3. Dung lượng của index

Một hệ có thể chuyển raw data sang object storage nhưng vẫn giữ search index rất lớn trên SSD. Capacity planning phải tính từng tier riêng.

### 37.4. Truy xuất dữ liệu lạnh

Restore/re-hydrate có thể có latency, egress cost và temporary hot-disk footprint. Nếu nhiều requests cùng đọc archive, cần admission và cache plan.

---

## 38. Chẩn đoán khi disk used tăng đột biến

Một quy trình ngắn:

1. Xác định **node/mount/volume** và metric source.
2. Xác nhận đây là bytes thực, không phải metrics reset/mount đổi.
3. So logical data count/growth và physical storage growth.
4. Kiểm deploy/batch/TTL/index/rebalance/snapshot/backup gần nhất.
5. Xem SSTables/segments/indexes/WAL/logs/temp.
6. Xem deleted/expired values đang chờ reclaim.
7. Kiểm bytes tăng ở table/collection/tenant nào.
8. Xem compaction/cleanup đang chạy hay stalled.
9. Đo thời gian tới threshold với worst-case growth.
10. Chọn biện pháp giảm tải/cleanup/mở rộng **không phá durability**.

### 38.1. Không giải phóng bằng tay tệp engine

Không tự xóa WAL, SSTables, journal, oplog, segment files hay snapshot metadata. Có thể làm database corruption hoặc mất recovery point. Chỉ dùng workflow/tooling được engine hỗ trợ và approved runbook.

### 38.2. Tìm root cause thay vì chỉ mở rộng

Nếu log retention bị tăng do CDC consumer offline, thêm 1 TiB disk có thể chỉ trì hoãn incident. Cần sửa consumer lag và chính sách retention/rebootstrap.

---

## 39. Chẩn đoán khi disk latency và p99 tăng

### Bước 1 — Phân biệt user-visible và disk-side latency

- API p99 tăng thật không?
- DB client request latency tăng?
- Device read/write latency tăng?
- Errors/retries có làm request kéo dài?

### Bước 2 — Xem saturation

- IOPS/throughput gần quota?
- Queue depth tăng?
- Disk busy time tăng?
- Instance-level volume cap/credits cạn?
- Một shard làm nóng node?

### Bước 3 — Xem tác vụ nền

- Compaction backlog?
- Snapshot/backup?
- TTL deletes?
- Index build/backfill?
- Replica catch-up?
- Rebalance/repair?
- JVM GC/OS memory pressure?

### Bước 4 — Đặt điều tra trên timeline

~~~text
02:10 backfill starts
02:11 disk read throughput climbs
02:11 write p99 increases
02:12 client retry attempts rise
02:15 backfill paused
02:16 disk queue drains
02:17 p99 improves
~~~

Đây là **tương quan gợi ý**, không tự chứng minh nhân quả; cần xem load khác và thử nghiệm có kiểm soát.

### Bước 5 — Giữ foreground SLO

Pause/throttle optional jobs, giới hạn in-flight/retries, giảm export traffic. Không tắt maintenance cốt lõi vô thời hạn nếu sẽ làm compaction debt tăng.

### Bước 6 — Sau sự cố

Đo pending work có được trả hết không, free space có đủ cho failover không, correctness/retention có bị ảnh hưởng không.

---

## 40. Khi disk đầy mà không thể mở rộng ngay

Ưu tiên các thao tác an toàn theo engine/workload:

- Tạm dừng non-critical bulk ingest/backfill/export.
- Giảm retry storm.
- Chặn thêm công việc làm đầy disk.
- Xác định logs/backups thực sự có thể rotate **theo chính sách**, không delete tùy tiện.
- Xem index không dùng có thể drop **qua quy trình đã duyệt** và đánh giá ảnh hưởng query.
- Kiểm TTL/retention cleanup đang chậm vì điều gì.
- Tăng dung lượng volume hoặc thêm capacity với kế hoạch bootstrap.
- Đảm bảo remaining disk đủ cho compaction/recovery.
- Kiểm watermark và read-only/write-reject behavior.

### 40.1. Không giảm replication như phản xạ đầu tiên

Thay RF/quorum/replicas có thể làm giảm độ bền, availability và thay đổi phân phối dữ liệu. Đây là thay đổi kiến trúc, không là thao tác dọn disk bình thường.

### 40.2. Không giảm tombstone grace thiếu hiểu biết

Trong Cassandra, giảm GC grace quá mạnh có thể gây zombie data nếu replica offline chưa repair.

### 40.3. Không xóa latest backup tùy tiện

Backup là nguồn khôi phục khi disk/node mất; việc xóa phải theo retention/recovery policy và biết bản khôi phục còn hợp lệ.

### 40.4. Admission tốt hơn queue vô hạn

Nếu source không thể phục vụ thêm writes/reads, reject/defer có kiểm soát và thông báo đúng lỗi, thay vì giữ vô hạn requests rồi crash vì memory/disk.

---

## 41. Ma trận kiểm thử dung lượng và I/O

| ID | Kịch bản | Tín hiệu cần đo | Oracle |
|---|---|---|---|
| C01 | Insert-only steady load | Logical/physical growth | ETA ổn định, backlog bounded |
| C02 | Update cùng hot keys | WA, IOPS, old versions | Không mất writes, no uncontrolled bloat |
| C03 | Bulk delete | Tombstone, disk reclaim | Logical deletion đúng, cleanup eventual |
| C04 | TTL synchronized burst | Expiry/deletion workload | SLO trong budget, no invalid reads |
| C05 | TTL spread with jitter/buckets | IO profile | Ít spike, data expiry semantics đúng |
| C06 | New secondary index | Index bytes, backfill I/O | Cutover chỉ khi ready |
| C07 | Cassandra compaction backlog | SSTables/pending tasks | Không kéo dài debt vô hạn |
| C08 | Cassandra replica offline | Tombstones/repair | Không zombie data |
| C09 | MongoDB checkpoint/eviction | Dirty pages, disk latency | p99 và recovery đúng |
| C10 | MongoDB TTL mass delete | Oplog/replication lag | CDC không mất delete |
| C11 | Redis AOF rewrite | Disk/RSS/fork | Không OOM/persistence corruption |
| C12 | Redis maxmemory evictions | Memory/eviction counters | Cache miss fallback đúng |
| C13 | DynamoDB GSI backfill | Capacity/throttle/index status | No breaking serving path |
| C14 | Elasticsearch segment merge | Segments/merge bytes | Search p99 within budget |
| C15 | Disk IOPS capped | Queue/latency/throttles | Bounded requests, graceful rejection |
| C16 | Disk bandwidth capped | MiB/s/await | Không nhân retries vô hạn |
| C17 | Disk 90% full in staging | Compaction/temp headroom | Safe read/write/recovery policy |
| C18 | Node fails during rebalance | Per-node free/catch-up | Capacity đủ N+1 scenario |
| C19 | Snapshot/backup overlap | Disk/CPU/network | Foreground SLO preserved |
| C20 | Old backup restored | Deletion replay/versions | Không hồi sinh dữ liệu đã xóa |
| C21 | CDC consumer lag | Log retention/disk | Rebootstrap khi vượt window |
| C22 | App retry storm | Attempts/queue | Retry budget enforced |
| C23 | One tenant grows 10× | Per-shard growth/heat | Fairness/capacity alert |
| C24 | Filesystem mount changes | Metric labels | No false capacity forecast |
| C25 | `df` high, `du` low | Open files/reserved bytes | Root cause xác định, no blind delete |
| C26 | Short benchmark vs long | Debt and p99 | Sustainable capacity reported |
| C27 | Remote archive tier migration | Hot/remote bytes, restore | Retrieval/deletion contract kept |
| C28 | Physical write heavy, net growth 0 | Bytes written/WA | Disk pressure detected |
| C29 | Disk almost full plus index build | Temporary space | Job stops before unsafe operation |
| C30 | Two app versions dual-write | Storage growth/index size | Migration headroom and rollback |
| C31 | LSM snapshots block GC | Old files and compaction | Snapshot lifecycle corrected |
| C32 | Multi-region replica addition | Egress, per-region storage | DR sizing and consistency preserved |

Tất cả thao tác gây hỏng cluster, disk-full, forced node loss, GC/compaction tuning hay failure injection cần được triển khai trong **staging/disposable environment đã được cho phép**, không làm trên production để thử.

---

## 42. Bài tập 1 — Phân biệt các số đo

Một node báo:

~~~text
Logical live data:  450 GiB
Storage allocated:  690 GiB
Filesystem used:    810 GiB
Filesystem size:   1024 GiB
Filesystem avail:   190 GiB
~~~

1. Vì sao các giá trị khác nhau?
2. 120 GiB giữa filesystem used và storage allocated có thể là gì?
3. Vì sao `size - used` có thể khác `avail`?
4. Hãy tính space amplification theo phạm vi physical/logical đã chọn.
5. Nếu compaction cần thêm 250 GiB temporary space, node có đủ không?
6. Alert nào nên phát dù filesystem chưa đầy?

---

## 43. Bài tập 2 — Dự báo thời gian chạm ngưỡng

Một shard có:

~~~text
Usable capacity:  4 TiB
Current used:     2.5 TiB
Growth net:       60 GiB/day
Safe threshold:   80%
```

1. Tính threshold GiB.
2. Tính headroom tới threshold.
3. Tính ngày tới ngưỡng bằng mô hình tuyến tính.
4. Nếu compaction cần temporary 400 GiB, ngưỡng 80% có còn đủ?
5. Nếu growth tăng 50% sau campaign, ETA đổi thế nào?
6. Vì sao cần thêm dự báo worst-case theo node?

---

## 44. Bài tập 3 — Capacity với replication và indexes

Một dataset logical 2 TiB có:

~~~text
Compression ratio: 0.5
Indexes: 0.25 TiB mỗi replica
RF: 3
Logs + snapshots + temp toàn cluster: 0.7 TiB
```

1. Ước lượng physical storage với công thức trong bài.
2. Nếu 6 nodes dung lượng usable 1 TiB/node, có đủ không?
3. Nếu một node hỏng, nodes còn lại có đủ space khi rebalance?
4. Nếu schema thêm một index 0.1 TiB/copy, overhead tăng bao nhiêu?
5. Cần thêm margin nào khi lưu dữ liệu cũ và mới song song?

---

## 45. Bài tập 4 — IOPS, throughput và latency

Cho:

~~~text
Disk read bandwidth:  240 MiB/s
Disk read IOPS:       30.720/s
Average read latency: 8 ms
```

1. Average read size là bao nhiêu KiB?
2. Nếu read IOPS tăng gấp đôi còn throughput gần như giữ nguyên, kích thước I/O thay đổi thế nào?
3. Vì sao latency 8 ms không suy được p99?
4. Little's Law cho số I/O trung bình đang trong hệ nếu trạng thái ổn định?
5. Nếu queue length tăng liên tục, có thể dùng Little's Law đơn giản để khẳng định hệ vẫn ổn định không?

---

## 46. Bài tập 5 — Cassandra compaction và disk full

Một cụm Cassandra có:

~~~text
Node A disk 88% used.
Pending compaction high.
TTL-heavy table.
Replica B offline long.
Snapshot storage growing.
```

Yêu cầu:

1. Tìm các nhóm metrics cần thu.
2. Xác định vì sao không xóa SSTables thủ công.
3. Vì sao không giảm `gc_grace_seconds` vội?
4. Kiểm repair/reseed và tombstone lifecycle thế nào?
5. Đánh giá snapshot cleanup policy.
6. Mở rộng dung lượng có cần headroom cho bootstrap/streaming?
7. Tạo một kế hoạch giảm foreground/backfill load mà không làm mất dữ liệu.

---

## 47. Bài tập 6 — MongoDB dữ liệu đã xóa nhưng disk không giảm

Một MongoDB collection xóa 80% documents nhưng `storageSize` không giảm tương ứng.

1. Phân biệt `dataSize`, `storageSize`, `totalIndexSize`, filesystem used.
2. Cơ chế space reuse của WiredTiger có vai trò gì?
3. Tại sao `compact` không nên chạy như câu trả lời mặc định?
4. TTL cleanup có thể còn đang chạy không?
5. Backup/snapshot/oplog có chiếm disk riêng không?
6. Index build trong lúc này tác động I/O ra sao?
7. Điều kiện nào cho phép đánh giá physical space reclaim?

---

## 48. Bài tập 7 — Thiết kế dashboard và alert Prometheus

Thiết kế dashboard cho một NoSQL cluster tự quản gồm:

- Filesystem used/available và ETA theo node.
- Read/write MiB/s và IOPS.
- Disk latency/queue/busy time.
- Database p99, errors/retries.
- Compaction/TTL/index/backup metrics.
- Growth 1d/7d/30d.
- Worst shard/tenant cohort.
- Forecast có confidence caveats.
- Link tới runbook và owner.
- Alert watch/warning/critical.

Viết PromQL cho những metrics thực có. Ghi rõ vì sao **host disk busy fraction không tự là percentage maximum NVMe bandwidth**.

---

## 49. Bài tập 8 — Kế hoạch retention và archive

Một dịch vụ analytics lưu 30 GiB compressed events/day và giữ 365 ngày, với RF=3.

1. Ước lượng logical live data theo retention.
2. Ước lượng physical replicated data trước indexes/logs.
3. Nếu chuyển dữ liệu trên 90 ngày sang object storage, hot live-set còn bao nhiêu?
4. Archive retrieval có cần SLA gì?
5. Có phải giữ search index cho data lạnh không?
6. Delete/PII propagation đến archive/backups như thế nào?
7. Khi chuyển storage tier, peak temporary bytes và network cost cần tính gì?
8. Xây forecast trước và sau khi đổi retention policy.

---

## 50. Những ngộ nhận thường gặp

| Ngộ nhận | Điều đúng hơn |
|---|---|
| “Cluster còn 25% free nên an toàn.” | Một node/shard có thể gần đầy |
| “Dung lượng data trong DB bằng dung lượng file trên OS.” | Index/log/snapshot/temp/replicas khác scope |
| “Nhiều DELETE thì disk giảm ngay.” | Compaction/space reuse/GC cần thời gian |
| “Filesystem used và avail luôn bổ sung đúng bằng size.” | Reserved/quota/metadata có thể khác |
| “`df` và `du` phải luôn bằng nhau.” | Open-deleted files, mount, snapshots... |
| “Write amplification chỉ tác động latency.” | Tăng physical bytes, I/O, SSD wear |
| “Net storage không tăng nghĩa disk không bận.” | Update churn vẫn ghi rất nhiều |
| “Tăng trưởng tuần qua đủ dự báo mọi thời điểm.” | Mùa vụ, batch, compaction và policy đổi |
| “Disk 80% luôn cần tăng volume ngay.” | Phải xét ETA, headroom và maintenance |
| “Chỉ monitor cluster sum.” | Worst node/shard quyết định outage |
| “Replication RF=3 chỉ nhân payload 3 lần.” | Index/log/temp/overheads còn khác |
| “Thêm node là disk skew tự sửa ngay.” | Rebalancing có thời gian/tài nguyên |
| “Disk IOPS cao luôn là throughput cao.” | I/O size quyết định MiB/s |
| “`%util=100` trên NVMe nghĩa đã dùng hết performance.” | Multi-queue device cần thêm latency/quota |
| “Disk latency chính là API latency.” | Network/queue/replica/retries cộng thêm |
| “Queue tăng không sao nếu QPS ổn.” | Có thể đang backlog và p99 xấu |
| “Thêm client threads chữa disk saturation.” | Có thể tạo thêm queue/retries |
| “Compaction không liên quan dung lượng tạm.” | Input/output có thể cùng tồn tại |
| “Giảm compaction mạnh là tốt mãi.” | Debt và disk-used có thể tăng |
| “DynamoDB có disk usage metric như Cassandra.” | Managed service expose khác |
| “Redis persistence disk đủ nghĩa cache memory đủ.” | Memory/maxmemory là bottleneck riêng |
| “MongoDB `storageSize` phải giảm sau DELETE.” | WiredTiger có space reuse |
| “Elasticsearch primary size đã gồm mọi replicas.” | Phải kiểm metric scope |
| “GC của Java là GC tombstone của DB.” | Hai tầng khác nhau |
| “Snapshot size bằng disk bytes thêm.” | Có thể hardlink/CoW/dedup |
| “Forecast tuyến tính chính xác tuyệt đối.” | Cần scenario và margin |
| “PromQL `rate` của gauge là tốt hơn `deriv`.” | Counters/gauges có semantics riêng |
| “Disk alert chỉ cần used percent.” | Cần ETA, IOPS, queue, maintenance |
| “Storage scaling không ảnh hưởng network.” | Bootstrap/replica transfer có thể rất nặng |
| “Backup trong cùng volume đủ DR.” | Có cùng failure domain |
| “Xóa WAL/snapshot bằng `rm` để lấy chỗ.” | Có thể phá crash recovery và dữ liệu |

---

## 51. Checklist giám sát dung lượng và tải đĩa

- [ ] Phân biệt logical data, compressed storage, physical allocation và filesystem available.
- [ ] Biết metric nào đã gồm indexes/replicas/snapshots.
- [ ] Có per-node/per-shard disk-used và available bytes.
- [ ] Có growth 1d/7d/30d và forecast theo worst node.
- [ ] Có headroom policy cho compaction, backup và failover.
- [ ] Có per-node read/write IOPS và MiB/s.
- [ ] Có disk latency/queue cùng cloud volume quota/credits nếu áp dụng.
- [ ] Không dùng `%util` đơn độc làm bằng chứng NVMe saturation.
- [ ] Có dashboard compaction/flush/TTL/repair/index build.
- [ ] Có application p99/goodput/retry/throttle metrics.
- [ ] Có storage size theo table/collection/index/tenant cohort phù hợp.
- [ ] Có alerts dựa trên ETA và thời gian cấp thêm capacity.
- [ ] Theo dõi log/oplog/WAL/CDC retention và backup footprint.
- [ ] Phân biệt Redis memory metrics với persistence disk metrics.
- [ ] DynamoDB dùng service size/capacity/throttle metrics phù hợp.
- [ ] Elasticsearch phân biệt primary và total replica storage.
- [ ] MongoDB phân biệt dataSize/storageSize/indexSize/WT/cache.
- [ ] Cassandra không cleanup tombstones thiếu repair policy.
- [ ] Không xóa engine files thủ công để giảm disk.
- [ ] Benchmark đủ dài để maintenance backlog ổn định.
- [ ] Capacity plan có kịch bản peak, node loss, region loss, backfill.
- [ ] Không tạo high-cardinality labels từ IDs không giới hạn.
- [ ] Rà soát alerts khi volume/mountpoint hoặc topology thay đổi.
- [ ] Có runbook và owners cho critical disk alerts.
- [ ] Sau incident đo lại accuracy của growth forecast.
- [ ] Không hy sinh durability, retention và deletion correctness để có disk đẹp.

---

## 52. Tổng kết

**Quan sát dung lượng NoSQL là bài toán về thời gian, vị trí và tải — không phải chỉ là một phần trăm sử dụng ổ đĩa.** Một chỉ số disk còn trống không cho biết khi nào node sẽ đầy, cũng không cho biết thiết bị có chịu được compaction, replication và I/O foreground hay không.

Các nguyên tắc cần nhớ:

1. **Đo dung lượng theo đúng scope**: logical live data khác physical files, filesystem usage và managed service storage quotas.
2. **Tính compression, index, replication, WAL, snapshots, tombstones và temporary compaction space** khi lập capacity plan.
3. **Dự báo từ growth rate và headroom**, theo nhiều cửa sổ thời gian và kịch bản, không coi tuyến tính là lời tiên tri.
4. **Worst node/shard quan trọng hơn cluster average**, nhất là khi dữ liệu bị skew hoặc cluster đang failover.
5. **Disk IOPS, MiB/s, latency và queue là các trục riêng**. Disk rảnh dung lượng vẫn có thể bão hòa I/O.
6. **Compaction, GC, TTL, backup, repair và index build tạo tải nền**; phải đo cùng foreground p99/goodput.
7. **Mỗi NoSQL expose metrics khác nhau**: Cassandra SSTables, MongoDB WiredTiger, Redis memory/AOF, DynamoDB service capacity, Elasticsearch Lucene segments.
8. **Deletion không đồng nghĩa reclaim tức thì**; cần hiểu lifecycle và không xóa file engine ngoài quy trình.
9. **Alerts nên phản ánh thời gian để hành động**, không chỉ một threshold phần trăm.
10. **Sustained performance cần trả đủ maintenance debt** và giữ data correctness, replication, backup/recovery không bị phá vỡ.

**Câu cần nhớ: “Đừng chỉ hỏi còn bao nhiêu GB. Hãy hỏi GB đó nằm ở node nào, tăng nhanh đến đâu, cần chừa bao nhiêu cho compaction và failover, thiết bị đang chịu bao nhiêu I/O, và hệ còn bao lâu để hành động trước khi người dùng bị ảnh hưởng.”**
