# Tính băng thông ghi, đọc, nhân bản và phục hồi

Hoạch định năng lực Kafka không dừng ở việc cộng dung lượng payload mà producer gửi. Mỗi record có thể được ghi trên nhiều broker theo replication factor, được đọc bởi nhiều consumer group độc lập, được lưu trong thời gian retention và phải được nhân bản lại sau khi broker hoặc replica gặp sự cố. Nếu chỉ tính băng thông ghi đầu vào, cluster có thể đủ sức nhận dữ liệu lúc bình thường nhưng thiếu network, disk hoặc thời gian phục hồi khi tải tăng hay một node quay lại.

Một capacity plan nên trả lời bốn câu hỏi:

1. **Write:** producer đưa vào bao nhiêu byte/record mỗi giây và broker phải ghi bao nhiêu bản sao?
2. **Read:** có bao nhiêu consumer group đọc toàn bộ hoặc một phần luồng dữ liệu?
3. **Replication:** broker phải truyền bao nhiêu byte giữa leader và follower, cả khi bình thường lẫn khi ISR cần bắt kịp?
4. **Recovery:** nếu replica bị trễ hoặc broker phải dựng lại dữ liệu, cần bao nhiêu băng thông để phục hồi trong thời gian mục tiêu?

Các phép tính dưới đây là mô hình ban đầu. Số liệu cuối cùng phải được hiệu chỉnh bằng benchmark trên workload thật, vì batch size, compression, phân bố key, partition placement, TLS, storage và traffic burst đều ảnh hưởng đến kết quả.

## 1. Chuẩn hóa đơn vị và đầu vào

Trước khi tính, thống nhất cách biểu diễn:

| Đại lượng | Ký hiệu | Đơn vị |
|---|---|---|
| Tốc độ event đầu vào | `R` | records/s |
| Kích thước record trung bình trước compression | `S` | bytes/record |
| Băng thông logic | `B_logical` | bytes/s hoặc MB/s |
| Hệ số dung lượng sau compression | `C` | tỷ lệ, ví dụ 0,5 nghĩa là còn 50% |
| Băng thông record batch lưu trên log | `B_store` | bytes/s |
| Replication factor | `RF` | số replica |
| Số consumer group đọc dữ liệu | `G` | groups |
| Retention | `T` | seconds |
| Thời gian phục hồi mục tiêu | `T_recovery` | seconds |

Trong bài này, `1 MB = 1.000.000 bytes`, `1 GB = 1.000 MB`, `1 TB = 1.000 GB`. Nếu hệ thống báo MiB/GiB/TiB thì phải quy đổi theo cơ số 1024; không trộn đơn vị thập phân và nhị phân trong cùng phép tính.

Kích thước record cần tính cả key, value, headers và phần framing/serialization có liên quan. Nếu chỉ lấy kích thước JSON value, kết quả sẽ thấp hơn thực tế. Với workload record rất nhỏ, protocol và request overhead có thể chiếm tỷ lệ đáng kể dù tổng payload byte thấp.

## 2. Tính băng thông ghi logic từ producer

Nếu producer phát `R` record mỗi giây và kích thước trung bình mỗi record là `S` byte:

\[
B_{logical} = R \times S
\]

Ví dụ producer gửi 40.000 record/s, mỗi record trung bình 500 bytes:

\[
B_{logical} = 40.000 \times 500 = 20.000.000\ bytes/s = 20\ MB/s
\]

Đây là băng thông logic trước compression. Với nhiều topic, tính riêng từng topic hoặc từng workload rồi cộng lại:

\[
B_{logical,total} = \sum_{i=1}^{n} R_i \times S_i
\]

Không nên chỉ dùng average toàn cluster. Một topic có payload lớn hoặc burst cao có thể quyết định capacity của broker leader dù tổng average vẫn thấp.

### Từ băng thông trung bình sang peak bandwidth

Hệ thống thường có giờ cao điểm, batch job hoặc event burst. Có thể mô hình hóa:

\[
B_{peak} = B_{average} \times F_{peak}
\]

`F_peak` là hệ số peak lấy từ traffic profile thực tế, không phải hằng số chung. Ví dụ average 20 MB/s, peak factor đo được là 2,5 thì write peak cần dự trù 50 MB/s logic. Nếu có burst ngắn, cần đo cả cửa sổ 1 giây, 1 phút và 5 phút; average theo ngày không phản ánh được burst làm đầy producer buffer hoặc broker request queue.

## 3. Tính ảnh hưởng của compression

Kafka producer nén record batch trước khi gửi. Gọi `C` là tỷ lệ byte sau nén so với byte trước nén:

\[
B_{store} = B_{logical} \times C
\]

Ví dụ 20 MB/s logic với compression ratio `C = 0,5`:

\[
B_{store} = 20 \times 0,5 = 10\ MB/s
\]

Trong ví dụ này, broker nhận và lưu khoảng 10 MB/s record batch đã nén cho một bản sao leader, chưa tính protocol overhead và các metadata khác.

Không được giả định mọi payload đều nén được 50%. JSON lặp lại nhiều field thường nén tốt hơn payload đã nén hoặc dữ liệu entropy cao. Nên đo `compression-rate-avg` trên producer với dữ liệu đại diện. Giá trị metric có thể được biểu diễn theo tỷ lệ khác nhau tùy client/exporter; kiểm tra unit trước khi dùng trong công thức.

Compression giảm network và disk bytes nhưng tiêu tốn CPU ở producer/broker/consumer. Nếu CPU trở thành bottleneck, tăng compression có thể làm throughput giảm dù byte truyền ít hơn. Hãy benchmark `none`, `gzip`, `snappy`, `lz4` hoặc `zstd` theo workload và phiên bản client/broker.

## 4. Tính băng thông nhân bản theo replication factor

Với replication factor `RF`, mỗi record batch được lưu trên một leader và `RF - 1` follower replica. Bỏ qua overhead, tổng lượng byte được ghi lên disk trên toàn cluster xấp xỉ:

\[
B_{disk,cluster} = B_{store} \times RF
\]

Lượng replication payload được leader gửi sang follower, tính mỗi bản sao một lần, xấp xỉ:

\[
B_{replication} = B_{store} \times (RF - 1)
\]

Ví dụ `B_store = 10 MB/s`, `RF = 3`:

- Leader nhận producer batch: khoảng 10 MB/s.
- Hai follower nhận bản sao: tổng khoảng 20 MB/s.
- Tổng disk write trên ba replica: khoảng 30 MB/s.
- Replication payload leader-to-follower: khoảng 20 MB/s trên toàn cluster.

Ở góc nhìn NIC, tổng bytes gửi của leader cho replication và tổng bytes nhận của follower đều khoảng 20 MB/s. Nếu cộng cả inbound và outbound trên mọi broker, replication traffic có thể bị đếm hai lần. Khi làm capacity plan, phải ghi rõ đang đếm payload một chiều, bytes sent hay bytes received.

`RF` không có nghĩa mọi broker đều ghi `RF` bản sao. Mỗi partition có một leader và các follower trên broker khác; một broker có thể làm leader cho một số partition và follower cho các partition khác. Capacity per broker phụ thuộc replica placement và leader distribution.

## 5. Tính băng thông đọc theo consumer group

Trong consumer group truyền thống, các consumer member trong cùng group chia partition với nhau. Nếu group đọc toàn bộ topic, tổng dữ liệu group đọc xấp xỉ một lần luồng dữ liệu, không nhân với số member.

Ngược lại, các consumer group độc lập thường đọc cùng một luồng riêng biệt. Nếu có `G` group đều đọc toàn bộ topic:

\[
B_{consumer} \approx B_{store} \times G
\]

Ví dụ bốn consumer group độc lập cùng đọc toàn bộ topic có `B_store = 10 MB/s`:

\[
B_{consumer} \approx 10 \times 4 = 40\ MB/s
\]

Nếu group chỉ đọc một tập topic/partition hoặc chỉ nhận một phần dữ liệu do kiến trúc upstream, cần tính theo phần thực tế thay vì nhân nguyên luồng. Filter ở consumer thường không giảm lượng byte broker đã gửi nếu filter xảy ra sau khi fetch.

Một group replay offset cũ, chạy lại batch hoặc đọc lại dữ liệu có thể tạo read traffic bổ sung. Khi tính peak read, cần cộng replay workload vào số group tiêu thụ thường xuyên.

### Read bandwidth và broker egress

Consumer fetch traffic thường là tải đọc lớn nhất của broker. Với nhiều group, cùng một record batch có thể được truyền nhiều lần đến các group khác nhau. Vì vậy, write rate thấp không đảm bảo network egress thấp.

Ví dụ một topic ghi 10 MB/s đã nén, có 6 consumer group độc lập đọc toàn bộ:

\[
B_{consumer} = 10 \times 6 = 60\ MB/s
\]

Đây là egress payload ước lượng trước protocol/TLS overhead. Cần benchmark để xác định compression có được giữ trên đường fetch, mức fetch batching và phân bố consumer trên broker.

## 6. Tách tải mạng client và inter-broker

Capacity mạng của cluster cần ít nhất hai luồng:

- **Client traffic:** producer gửi dữ liệu vào leader; consumer fetch dữ liệu từ broker.
- **Inter-broker traffic:** leader gửi replica data cho follower; broker có thể còn trao đổi metadata/control và các traffic vận hành khác.

Một mô hình tổng quan một chiều:

\[
B_{network,in} \approx B_{producer} + B_{replication,receive}
\]

\[
B_{network,out} \approx B_{consumer} + B_{replication,send}
\]

Trong đó `B_replication,receive` và `B_replication,send` đều gần `B_store × (RF-1)` ở quy mô toàn cluster trong trạng thái cân bằng. Chúng không phải hai khoản payload khác nhau; đó là hai đầu của cùng luồng replication.

Với ví dụ 10 MB/s stored write, RF=3, bốn group đọc toàn bộ:

| Hạng mục | Băng thông payload ước lượng |
|---|---:|
| Producer ingress | 10 MB/s |
| Follower replication receive | 20 MB/s |
| Consumer egress | 40 MB/s |
| Leader replication send | 20 MB/s |

Cluster có thể cần tổng inbound khoảng 30 MB/s và outbound khoảng 60 MB/s, chưa kể overhead. Không lấy tổng 90 MB/s rồi gán cho một interface; cần phân bố theo broker, NIC và hướng traffic.

TLS, TCP/IP, request header, acknowledgement, retransmission, cross-rack routing và traffic quản trị tạo thêm overhead. Hệ số overhead nên được đo trên hạ tầng thật; không dùng một tỷ lệ cố định cho mọi môi trường.

### Ước lượng disk read và disk write

Disk bandwidth không đồng nhất với network bandwidth. Kafka có thể phục vụ fetch từ OS page cache, vì vậy broker gửi 40 MB/s cho consumer không có nghĩa disk phải đọc vật lý đúng 40 MB/s.

Ở trạng thái ổn định, tổng log write trên cluster có baseline:

\[
B_{disk,write} \approx RF \times B_{store}
\]

Leader còn đọc log để phục vụ consumer fetch và follower replication. Nếu phần lớn fetch được phục vụ từ leader, read demand trước cache có thể ước lượng:

\[
B_{read,demand} \approx B_{consumer} + B_{replication}
\]

Nếu `H_cache` là tỷ lệ byte được phục vụ từ page cache, physical disk read có thể ước lượng sơ bộ:

\[
B_{disk,read} \approx B_{read,demand} \times (1-H_{cache})
\]

Đây là mô hình gần đúng để lập kế hoạch, không phải công thức đo chính xác. `H_cache` phải được suy ra từ metric hệ điều hành/broker và workload; cache hit theo request không nhất thiết bằng cache hit theo byte. Nếu consumer fetch được phục vụ từ follower nhờ replica selection/rack-aware fetching, tải read sẽ phân bố khác giữa leader và follower.

Compaction, index access, log recovery và replica rebuild tạo thêm disk read/write ngoài baseline. Kafka append log chủ yếu là ghi tuần tự, nhưng filesystem, page cache, flush, compaction và storage device quyết định IOPS/latency thực tế. Hãy benchmark đồng thời sequential throughput, random read, fsync/flush behavior và disk latency trên loại volume production.

## 7. Tính dung lượng lưu trữ theo retention

Với topic dùng `cleanup.policy=delete`, lưu lượng ghi đã nén ổn định `B_store` và retention `T` giây, dung lượng cho một replica xấp xỉ:

\[
D_{one\ replica} = B_{store} \times T
\]

Tổng dung lượng log trên toàn cluster:

\[
D_{cluster} = B_{store} \times T \times RF
\]

Với nhiều topic có retention và replication factor khác nhau:

\[
D_{cluster} = \sum_{i=1}^{n} B_{store,i} \times T_i \times RF_i
\]

Sau đó áp dụng hệ số dữ liệu phụ `F_data` cho index, segment, thời gian xóa thực tế, compaction lag và biến động kích thước:

\[
D_{estimate} = D_{cluster} \times F_{data}
\]

Cuối cùng, nếu chỉ muốn sử dụng tối đa tỷ lệ `U` của dung lượng đĩa đã cấp phát:

\[
D_{provisioned} = \frac{D_{estimate}}{U}
\]

`F_data` và `U` phải được chọn theo kinh nghiệm vận hành và benchmark. Ví dụ `U=0,7` nghĩa là chỉ lập kế hoạch dùng 70% dung lượng raw, để còn không gian cho recovery, log segment mới, compaction và dao động tải. Đây là giả định planning, không phải giới hạn Kafka bắt buộc.

### Ví dụ tính dung lượng 7 ngày

Giả sử:

- Băng thông logic: 20 MB/s.
- Hệ số sau compression: `C = 0,5`, do đó `B_store = 10 MB/s`.
- Retention: 7 ngày = 604.800 giây.
- Replication factor: 3.
- Hệ số dữ liệu phụ: `F_data = 1,2`.
- Mức sử dụng đĩa mục tiêu: `U = 0,7`.

Dung lượng một replica:

\[
10\ MB/s \times 604.800s = 6.048.000\ MB = 6,048\ TB
\]

Dung lượng log toàn cluster:

\[
6,048\ TB \times 3 = 18,144\ TB
\]

Sau hệ số dữ liệu phụ:

\[
18,144\ TB \times 1,2 = 21,7728\ TB
\]

Dung lượng raw cần cấp phát ở mức sử dụng 70%:

\[
21,7728\ TB / 0,7 \approx 31,104\ TB
\]

Nếu có 6 broker và phân bố hoàn toàn cân bằng, trung bình khoảng 5,184 TB raw disk mỗi broker. Thực tế cần xem replica placement, disk log directory, broker skew và dung lượng dự phòng khi mất một node; không nên chỉ lấy phép chia trung bình làm quyết định cuối cùng.

## 8. Những yếu tố làm công thức retention thay đổi

### Topic compacted

Với `cleanup.policy=compact`, dữ liệu cũ được giữ hoặc loại bỏ theo key và trạng thái compaction, không đơn giản bằng write rate nhân retention time. Dung lượng phụ thuộc:

- Số key duy nhất và kích thước value hiện tại.
- Tần suất cập nhật cùng key.
- Tỷ lệ tombstone và `delete.retention.ms`.
- Compaction lag, segment chưa được compact và tốc độ cleaner.
- Khả năng có cả `compact,delete`.

Với topic compacted, cần benchmark/quan sát kích thước log thực tế theo thời gian và dự trù không gian tạm cho compaction. Không dùng công thức retention delete thuần túy để sizing chính xác cho compacted topic.

### `retention.bytes` và segment

`retention.bytes` có thể giới hạn dung lượng theo partition; đây không phải giới hạn tổng cluster. `retention.ms`, `segment.bytes`, `segment.ms` và thời gian chạy cleaner/deletion ảnh hưởng thời điểm dữ liệu thực sự được xóa. Segment hiện hành chưa đóng có thể chưa đủ điều kiện xóa ngay khi vượt retention.

### Tiered storage

Nếu dùng tiered storage, tách rõ local log tier và remote object storage. Local disk có thể chỉ giữ một phần dữ liệu nóng, trong khi remote storage giữ dữ liệu dài hạn. Capacity plan phải tính thêm:

- Local retention và cache/hotset trên broker.
- Remote object storage theo retention và replication/erasure policy của nền tảng remote.
- Network egress/ingress giữa broker và remote storage.
- Chi phí fetch dữ liệu lạnh và thời gian phục hồi khi remote tier chậm.

Không nhân replication factor Kafka với remote storage lần nữa nếu nền tảng remote đã có replication riêng; cần hiểu semantics durability của từng lớp.

## 9. Phân bố dung lượng và băng thông theo broker

Tổng capacity cluster đủ không có nghĩa mỗi broker đủ capacity. Mỗi broker có thể giữ replica cho nhiều partition, làm leader của một số partition và phục vụ nhiều consumer fetch hơn các node khác.

Với `N` broker, ước lượng trung bình ban đầu:

\[
B_{broker,avg} = \frac{B_{cluster,total}}{N}
\]

Để tính worst-case, dùng hệ số skew `K_skew` dựa trên leader/replica placement hoặc số đo:

\[
B_{broker,peak} \approx B_{broker,avg} \times K_{skew}
\]

Không mặc định `K_skew = 1`. Nếu broker đang giữ nhiều leader partition hot hoặc consumer group tập trung kết nối một số broker, network/disk có thể mất cân bằng.

Nên đánh giá riêng:

- Producer ingress trên broker leader.
- Disk write cho leader append và follower replica append.
- Replication bytes sent/received.
- Consumer egress theo group và partition leader.
- Disk read/page cache hit và network NIC saturation.
- Số partition, số file segment và request rate.

Rack awareness giúp phân bố replica qua failure domain, nhưng có thể làm traffic cross-rack tăng. Khi tính network, phân biệt intra-rack và inter-rack để biết switch/uplink nào có thể thành bottleneck.

## 10. Tính băng thông phục hồi replica bị trễ

Phải phân biệt **catch-up replica còn dữ liệu cũ** với **rebuild replica rỗng hoặc mất dữ liệu**.

### Catch-up sau khi follower offline tạm thời

Nếu follower giữ nguyên log và chỉ bị offline trong `T_offline`, lượng dữ liệu mới phát sinh trong thời gian đó xấp xỉ:

\[
D_{backlog} = B_{partition,store} \times T_{offline}
\]

Đây là backlog ước lượng; cần cộng lag đã tồn tại trước khi offline và điều chỉnh theo compaction/retention nếu có.

Khi follower hoạt động lại, nó vừa phải nhận dữ liệu mới vừa phải xóa backlog cũ. Nếu mục tiêu catch-up trong `T_recovery`:

\[
B_{fetch,required} \approx B_{ongoing} + \frac{D_{backlog}}{T_{recovery}}
\]

`B_ongoing` là write rate tiếp tục phát sinh cho replica đó. Nếu follower chỉ fetch được bằng write rate hiện tại, nó sẽ giữ nguyên khoảng lag chứ không bắt kịp.

Ví dụ partition có write rate 10 MB/s, follower offline 30 phút và cần catch-up trong 10 phút:

\[
D_{backlog} = 10 \times 1.800 = 18.000\ MB = 18\ GB
\]

\[
B_{fetch,required} = 10 + 18.000/600 = 40\ MB/s
\]

Follower cần fetch khoảng 40 MB/s trong giai đoạn phục hồi: 10 MB/s để theo kịp dữ liệu mới và 30 MB/s để xóa backlog trong 10 phút. Đây là payload rate trước overhead, và cần kiểm tra leader có đủ disk read/network egress để phục vụ.

### Rebuild replica rỗng hoặc thay broker mất disk

Nếu replica mới không có log local hợp lệ, lượng cần copy có thể gần bằng toàn bộ dữ liệu partition được giao cho replica đó:

\[
D_{rebuild} = \sum_{p \in assigned\ partitions} D_{partition,p}
\]

Nếu muốn rebuild trong `T_recovery` và write vẫn tiếp tục:

\[
B_{rebuild,required} \approx \frac{D_{rebuild}}{T_{recovery}} + B_{ongoing}
\]

Đây là tải bổ sung lớn hơn nhiều so với catch-up follower offline ngắn. Nhiều replica rebuild đồng thời có thể làm leader disk read, broker egress và target disk write bão hòa. Nên giới hạn concurrency/reassignment throttle và dành headroom cho traffic client bình thường.

## 11. Tính khả năng drain consumer backlog

Consumer recovery cũng cần băng thông. Nếu consumer group có backlog `D_backlog` record hoặc byte, throughput xử lý bền vững là `B_process`, trong khi producer vẫn ghi mới ở tốc độ `B_in`:

\[
T_{drain} = \frac{D_{backlog}}{B_{process} - B_{in}}
\]

Công thức chỉ có ý nghĩa khi `B_process > B_in`. Nếu consumer chỉ xử lý được bằng hoặc thấp hơn tốc độ ingest, backlog không thể giảm khi producer vẫn tiếp tục gửi.

`D_backlog`, `B_process` và `B_in` phải cùng đơn vị: đều là record/records-per-second hoặc đều là byte/bytes-per-second. Không lấy backlog tính bằng record chia cho throughput tính bằng MB/s.

Ví dụ backlog 900 GB, consumer xử lý được 50 MB/s và producer tiếp tục ghi 20 MB/s:

\[
T_{drain} = \frac{900.000\ MB}{50-20\ MB/s} = 30.000s \approx 8,33h
\]

Nếu dừng producer, thời gian drain lý thuyết là `900.000 / 50 = 18.000s`, khoảng 5 giờ. Thời gian thực tế còn phụ thuộc partition skew, downstream, retry, transaction, rebalance và event size.

Lag theo offset không luôn đổi trực tiếp thành byte. Muốn tính recovery bandwidth, nên dùng byte lag hoặc ước lượng event age/record size theo partition. Topic compacted hoặc có retention có thể có khoảng trống offset; `log end offset - committed offset` không phải lúc nào cũng là số record còn tồn tại.

## 12. Sizing partition và consumer concurrency

Partition count ảnh hưởng đến parallelism, metadata, file segment, replication và khả năng phân bố tải. Số partition không nên chỉ chọn theo số broker.

Một ước lượng ban đầu:

\[
P_{required} = \max\left(
\left\lceil \frac{R_{peak}}{R_{partition,safe}} \right\rceil,
\left\lceil \frac{B_{peak}}{B_{partition,safe}} \right\rceil,
P_{parallelism}
\right)
\]

Trong đó:

- `R_partition,safe` là record/s bền vững đã benchmark cho một partition với payload và key distribution đại diện.
- `B_partition,safe` là MB/s bền vững cho một partition.
- `P_parallelism` là số partition cần để đạt consumer concurrency và phân bố leader mong muốn.

Đây là công thức sàng lọc ban đầu, không phải partition calculator chính xác. Cần kiểm tra số partition trên mỗi broker, số replica, leader balance, hot key và số consumer group.

Trong consumer group truyền thống, số consumer active tối đa cho một topic bị giới hạn bởi số partition được assign. Tăng consumer vượt số partition không tăng parallelism của group. Với workload cần nhiều worker hơn partition, Share Groups có thể phân phối record ở mức record nhưng phải chấp nhận ordering trade-off; không dùng chúng như một cách tăng song song miễn phí cho luồng cần strict per-key ordering.

## 13. Ví dụ capacity plan tổng hợp

Giả sử một hệ thống có:

- 40.000 event/s, kích thước trung bình 500 bytes.
- Compression factor đo được `C = 0,5`.
- `RF = 3`.
- Retention 7 ngày.
- 4 consumer group độc lập đọc toàn bộ topic.
- 6 broker, phân bố ban đầu giả định tương đối cân bằng.

| Hạng mục | Công thức | Kết quả ước lượng |
|---|---|---:|
| Logical producer write | 40.000 × 500 B | 20 MB/s |
| Stored/compressed write | 20 × 0,5 | 10 MB/s |
| Replication payload một chiều | 10 × (3−1) | 20 MB/s |
| Tổng cluster disk write | 10 × 3 | 30 MB/s |
| Consumer egress | 10 × 4 groups | 40 MB/s |
| Tổng inbound broker payload | Producer 10 + follower receive 20 | 30 MB/s |
| Tổng outbound broker payload | Consumer 40 + leader replication send 20 | 60 MB/s |
| Dung lượng log 7 ngày, toàn cluster | 10 MB/s × 604.800 × 3 | 18,144 TB |
| Dung lượng với hệ số phụ 1,2 | 18,144 × 1,2 | 21,773 TB |
| Raw disk ở mức sử dụng 70% | 21,773 / 0,7 | 31,104 TB |

Nếu chia đều cho 6 broker, raw disk trung bình khoảng 5,184 TB/broker. Inbound/outbound trung bình theo phép chia sáu lần lượt là 5 MB/s và 10 MB/s mỗi broker, nhưng đây chỉ là baseline lý thuyết. Broker giữ nhiều leader hoặc replica của partition nóng có thể cao hơn đáng kể.

Ví dụ này chưa cộng traffic của schema registry, Connect, Streams changelog, remote storage, replay ngoài bốn group, compaction và recovery đồng thời. Hãy bổ sung các workload đó thành dòng riêng trong bảng capacity plan.

## 14. Dự trù capacity khi mất một broker

Capacity plan không nên chỉ tính trạng thái đủ node. Khi một broker mất:

- Một phần replica trở nên unavailable hoặc under-replicated.
- Partition leader có thể chuyển sang broker khác.
- Producer/consumer traffic được phân bố lại.
- Follower replica có thể cần catch-up khi broker quay lại.
- Nếu broker được thay mới, replica trên node mới có thể phải rebuild từ leader.

Với `N` broker và tải phân bố hoàn toàn đều, mất một broker làm tải trung bình trên mỗi broker còn lại tăng theo hệ số:

\[
F_{N-1} = \frac{N}{N-1}
\]

Ví dụ 6 broker, mất một node làm tải trung bình lý thuyết trên 5 node còn lại tăng `6/5 = 1,2`, tức 20%. Nhưng nếu node bị mất đang giữ nhiều leader partition nóng, mức tăng có thể lớn hơn. Phải mô phỏng placement thật thay vì chỉ dựa vào trung bình.

Nếu cluster chỉ vừa đủ capacity ở trạng thái bình thường, nó có thể không chịu được một broker failure và đồng thời phục hồi replica. Cần định nghĩa rõ N+1 headroom: cluster có thể tiếp tục phục vụ peak workload trong lúc một broker offline hay chỉ giữ availability ở tải giảm?

## 15. Những yếu tố làm recovery chậm

| Yếu tố | Ảnh hưởng | Metric cần theo dõi |
|---|---|---|
| Leader disk read bão hòa | Không đọc đủ replica data để follower catch-up | Disk read throughput/latency, page cache |
| Target disk write chậm | Replica nhận dữ liệu nhưng ghi log không kịp | Disk write latency/IOPS, filesystem queue |
| Network uplink bão hòa | Fetch replica và client traffic tranh băng thông | NIC in/out, TCP retransmit, cross-rack traffic |
| Quá nhiều replica phục hồi cùng lúc | Nhiều leader cùng gửi dữ liệu, gây burst | ReplicationBytesOut/In, fetcher lag, broker request latency |
| Compression/CPU | Decompress/recompress hoặc TLS làm CPU tăng | CPU, GC, compression ratio, request handler idle |
| Partition skew | Một số partition nóng phục hồi chậm hơn | Per-partition lag, leader/replica placement |
| Consumer downstream chậm | Consumer backlog drain không đạt mục tiêu | Processing rate, database/API latency, retry |
| Retention/compaction | Segment bị xóa/compact trong khi follower cần bắt kịp có thể thay đổi lượng dữ liệu cần phục hồi | Log start/end offset, cleaner metrics, replica lag |

Replication throttle có thể bảo vệ traffic client bằng cách giới hạn tốc độ phục hồi, nhưng kéo dài thời gian catch-up. Không throttle có thể phục hồi nhanh hơn nhưng gây latency hoặc throughput degradation cho production traffic. Cần đặt mục tiêu recovery và client SLO cùng lúc.

## 16. Quy trình lập bảng capacity plan

1. Liệt kê topic, owner, peak records/s, average/peak record size, key distribution và compression.
2. Ghi replication factor, `min.insync.replicas`, retention, cleanup policy và partition count theo từng topic.
3. Tính logical write, stored write, disk write, replication payload và consumer egress.
4. Tính dung lượng theo retention; tách delete, compacted và tiered topics.
5. Phân bổ leader/replica lên từng broker và tính skew, rack traffic, disk/NIC per node.
6. Tính kịch bản mất một broker, follower offline, replica rebuild và consumer backlog drain.
7. Xác định headroom cho peak burst, recovery và maintenance; tránh dùng toàn bộ capacity đo được ở benchmark.
8. Chạy benchmark với payload, compression, RF, consumer groups và failure scenario đại diện.
9. Đối chiếu dự báo với `BytesIn/Out`, replication bytes, disk I/O, consumer lag và recovery time thực tế.
10. Cập nhật mô hình khi traffic, retention, số group hoặc schema/payload thay đổi.

## 17. Metrics nên thu thập để hiệu chỉnh mô hình

### Producer và broker

- Producer `record-send-rate`, `record-size-avg`, `compression-rate-avg`, `request-latency-avg`, retry và buffer wait.
- Broker `BytesInPerSec`, `BytesOutPerSec`, `MessagesInPerSec`.
- `ReplicationBytesInPerSec`, `ReplicationBytesOutPerSec`.
- Produce/Fetch request rate và request latency theo broker.
- Disk read/write throughput, latency, IOPS, page cache và filesystem usage.
- NIC throughput theo hướng, interface và rack.

### Consumer và recovery

- Consumer `records-consumed-rate`, fetch rate/bytes, records lag và event age.
- Processing completion rate, downstream latency và retry count.
- Replica fetcher lag, ISR shrink/expand, under-replicated partitions.
- Recovery duration, replica bytes copied và tốc độ catch-up.
- Changelog/Streams restore throughput nếu workload dùng stateful Kafka Streams.

Tên JMX metric có thể khác theo Kafka version và exporter. Hãy xác định đúng counter/gauge/meter và unit trước khi tính rate. Không cộng `BytesInPerSec` với `ReplicationBytesInPerSec` nếu metric tổng đã bao gồm replication traffic; kiểm tra định nghĩa MBean để tránh double count.

## 18. Checklist kiểm chứng capacity

- [ ] Tính write rate từ record/s và serialized record size thực tế.
- [ ] Đo compression ratio bằng payload đại diện.
- [ ] Tính replication disk/network theo RF của từng topic.
- [ ] Cộng read traffic của từng consumer group độc lập; không nhân theo số member trong cùng group.
- [ ] Tách client traffic và inter-broker traffic, inbound và outbound.
- [ ] Tính retention cho từng topic, gồm RF và cleanup policy.
- [ ] Tách compacted/tiered storage khỏi công thức delete retention đơn giản.
- [ ] Kiểm tra disk, NIC và leader/replica skew theo từng broker.
- [ ] Tính catch-up follower và full replica rebuild theo recovery time mục tiêu.
- [ ] Tính consumer drain time khi producer vẫn tiếp tục ghi.
- [ ] Mô phỏng mất một broker và maintenance window.
- [ ] Giữ headroom cho burst, replication recovery và compaction.
- [ ] Benchmark throughput/latency trong trạng thái bình thường và khi recovery chạy đồng thời.
- [ ] Cập nhật capacity plan theo số đo production, không giữ mãi giả định ban đầu.

## Tài liệu tham khảo

- [Apache Kafka Design: Replication, log retention và consumer model](https://kafka.apache.org/documentation/#design)
- [Apache Kafka Broker Configs: Log retention và replication](https://kafka.apache.org/documentation/#brokerconfigs)
- [Apache Kafka Monitoring: BrokerTopicMetrics và replication metrics](https://kafka.apache.org/documentation/#monitoring)
- [Apache Kafka Performance Tools](https://kafka.apache.org/documentation/#basic_ops_performance)

Capacity Kafka phải tính đồng thời write, read, replication, storage và recovery. Replication factor làm tăng disk write và inter-broker traffic; mỗi consumer group độc lập làm tăng read egress; retention quyết định dung lượng lưu; còn recovery cần băng thông vượt lên trên write rate đang tiếp diễn để xóa backlog. Khi mô hình được tính theo từng topic, phân bố theo từng broker và kiểm chứng bằng benchmark/failure test, cluster sẽ có đủ headroom để vừa phục vụ peak traffic vừa phục hồi sau sự cố.
