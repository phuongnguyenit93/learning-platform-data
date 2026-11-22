# Đo chi phí thu hồi dung lượng và ảnh hưởng tác vụ nền

Trong NoSQL, một bản ghi **không còn được truy vấn** chưa chắc đã được **giải phóng khỏi đĩa**. Dữ liệu có thể đã hết TTL, bị xóa hoặc được thay thế bởi phiên bản mới, nhưng byte cũ vẫn nằm trong file, chỉ mục, log, snapshot hoặc bản sao. Để thu hồi không gian, cơ sở dữ liệu phải thực hiện những công việc như **TTL cleanup, compaction, dọn tombstone, hợp nhất segment, garbage collection, xóa partition hoặc tái tổ chức file**.

Những công việc đó không miễn phí: chúng tiêu thụ **CPU, RAM, I/O đĩa, băng thông mạng và dung lượng tạm**, cạnh tranh với các thao tác đọc/ghi. Một chính sách retention có thể giúp bớt 100 GiB dữ liệu nhưng buộc hệ thống xử lý hàng trăm GiB hoặc vài TiB I/O. Ngược lại, nếu cố giảm mọi công việc nền để làm đẹp p99 API, backlog có thể tăng tới lúc đĩa đầy hoặc engine phải chặn ghi.

Trong chương **Vòng đời dữ liệu** của **Database No SQL**, bài học này tập trung vào việc **định nghĩa, đo lường và tối ưu chi phí thu hồi dung lượng**, đồng thời đánh giá **ảnh hưởng tác vụ nền tới độ trễ và khả năng vận hành**.

> **Phạm vi:** Tên cơ chế, chỉ số, chính sách TTL và compaction phụ thuộc sản phẩm/phiên bản. Những con số bên dưới là giả định và phép tính minh họa, **không phải benchmark hay giới hạn mặc định** của Cassandra, HBase, MongoDB, DynamoDB, Redis hoặc RocksDB.

## 1. Vòng đời dữ liệu có nhiều mốc, không chỉ một lệnh DELETE

Xét một tài liệu IoT được giữ 30 ngày:

~~~~json
{
  "eventId": "evt-903",
  "deviceId": "device-42",
  "eventTime": "2026-11-14T08:00:00Z",
  "temperature": 24.3,
  "expiresAt": "2026-12-14T08:00:00Z"
}
~~~~

Quá trình kết thúc vòng đời có thể trải qua các mốc:

~~~~text
T0  Ghi thành công
 |
T1  Đến hạn retention / TTL
 |
T2  Bản ghi không còn hợp lệ đối với truy vấn
 |
T3  Cleanup nhận diện bản ghi đủ điều kiện loại bỏ
 |
T4  Compaction/index cleanup tạo cấu trúc còn dữ liệu sống
 |
T5  File cũ không còn bị reader/snapshot tham chiếu
 |
T6  Không gian được tái sử dụng hoặc trả lại storage
~~~~

Đây là sơ đồ khái niệm; một engine có thể gộp, bỏ hoặc đảo thứ tự một số bước. Đặc biệt **T1, T2, T4 và T6 không nhất thiết cùng thời điểm**.

### 1.1. Bốn cách hiểu “dung lượng”

| Khái niệm | Ý nghĩa | Tại sao phải đo riêng? |
| --- | --- | --- |
| **Live logical data** | Dữ liệu đang có hiệu lực và cần phục vụ đọc | Cho biết quy mô nghiệp vụ hiện tại |
| **Expired/obsolete data** | Dữ liệu hết hạn, bị xóa hoặc phiên bản cũ nhưng chưa được thu hồi hết | Cho biết nợ lưu trữ và việc cần dọn |
| **Physical occupied bytes** | File, index, WAL, metadata và các block đang chiếm tài nguyên | Liên quan headroom và chi phí |
| **Reclaimed/reusable bytes** | Không gian đã thu hồi hoặc có thể dùng lại | Phân biệt tái sử dụng nội bộ với giảm file size |

Ví dụ, một storage engine có thể giữ nguyên file 200 GiB sau khi xóa nhiều document, nhưng báo 60 GiB **reusable free space** bên trong file. Nếu ứng dụng tiếp tục ghi và engine tái sử dụng phần đó, hệ thống đã có lợi ích lưu trữ dù biểu đồ kích thước file chưa giảm.

**Không đồng nhất** dung lượng logic, vùng trống có thể tái sử dụng, dung lượng file trên filesystem, dung lượng object storage và byte bị tính phí. Khi báo cáo “thu hồi được 100 GiB”, luôn ghi rõ **thu hồi ở tầng nào**.

### 1.2. Logical delete không chứng minh xóa vĩnh viễn

Dữ liệu không còn trả về API vẫn có thể xuất hiện trong **replica, snapshot, backup, commit log, CDC, search index, read model hoặc data lake**. Nếu có yêu cầu xóa dữ liệu nhạy cảm, cần quy trình riêng theo dõi và xác nhận trạng thái từng bản sao; không chỉ dựa vào TTL của bảng chính.

## 2. Compaction: tại sao xóa một ít dữ liệu có thể tốn rất nhiều I/O?

Trong họ **LSM-tree**, ghi thường đi qua log và memtable rồi được flush thành SSTable hoặc file có cấu trúc tương tự. Một cập nhật có thể tạo phiên bản mới mà không sửa trực tiếp mọi file chứa bản cũ; thao tác xóa có thể ghi **tombstone**.

Khi compaction chạy, engine thường phải:

1. Chọn một nhóm file cần hợp nhất.
2. Đọc file chứa cả dữ liệu sống lẫn dữ liệu cũ.
3. Giải mã/so sánh khóa, phiên bản và tombstone.
4. Giữ dữ liệu phải còn tồn tại, bỏ dữ liệu đủ điều kiện.
5. Ghi file mới; xóa file cũ khi an toàn.

~~~~mermaid
flowchart LR
    A["SSTable A: live + old value"] --> M["Compaction/merge"]
    B["SSTable B: live + tombstone"] --> M
    C["SSTable C: live"] --> M
    M --> D["SSTable mới: dữ liệu cần giữ"]
    A -.-> X["Xóa file cũ khi an toàn"]
    B -.-> X
    C -.-> X
~~~~

Giả sử đầu vào 600 GiB, chỉ 100 GiB được loại. Hệ thống vẫn có thể phải **đọc 600 GiB và ghi lại 500 GiB dữ liệu còn sống**. Lượng I/O nhiều hơn đáng kể so với lượng dữ liệu thu hồi. Tỷ lệ này còn phụ thuộc level, loại compaction, số file, độ pha trộn sống/chết, nén và snapshot.

### 2.1. Các tác vụ nền khác

| Tác vụ | Vai trò | Tài nguyên có thể tiêu thụ |
| --- | --- | --- |
| TTL/expiration cleanup | Tìm và dọn dữ liệu hết hạn | CPU, index scan, I/O, metadata |
| Compaction/merge | Hợp nhất file và loại phiên bản cũ | Read/write I/O, CPU nén, RAM |
| Tombstone cleanup | Loại bằng chứng xóa khi đủ an toàn | I/O, phụ thuộc trạng thái replica/repair |
| Index cleanup/rebuild | Dọn hoặc dựng lại chỉ mục | CPU, I/O, dung lượng tạm |
| Repair/anti-entropy | Đồng bộ dữ liệu giữa replica | Mạng, CPU, đĩa |
| Snapshot/backup cleanup | Bỏ bản lưu trữ cũ và tham chiếu file | Metadata, object operations, storage |
| Rebalance/resharding | Chuyển dữ liệu giữa node hoặc region | Mạng, đĩa, dung lượng dự phòng |
| Garbage collection/vacuum | Thu hồi block/extent không còn dùng | Quét metadata, copy/rewrite tùy engine |

**Công việc nền là một phần của workload**, dù không được tạo trực tiếp từ API người dùng.

## 3. TTL, DELETE, tombstone và xóa vật lý khác nhau

**TTL** đặt thời hạn hợp lệ; **DELETE** biểu thị yêu cầu xóa; **tombstone** có thể giữ dấu vết đã xóa để hòa giải replica; **compaction/cleanup** thực hiện nhiều công việc tổ chức lại và thu hồi vật lý.

| Cơ chế | Tác động lên kết quả đọc | Giải phóng dung lượng ngay? | Rủi ro nếu thiết kế sai |
| --- | --- | --- | --- |
| TTL | Bản ghi có thể được coi là hết hiệu lực tại deadline | Không bảo đảm | Trả dữ liệu quá hạn nếu đường đọc không áp dụng đúng |
| DELETE | Bản ghi có thể bị loại khỏi tập dữ liệu hiện hành | Không bảo đảm | Replica/index còn bản cũ |
| Tombstone | Ghi nhận thao tác xóa theo cơ chế engine | Bản thân tombstone cũng chiếm chỗ | Dọn quá sớm gây hồi sinh dữ liệu ở một số hệ |
| Compaction | Gộp file, dọn giá trị cũ đủ điều kiện | Có thể thu hồi khi file cũ được loại | Tranh I/O, thiếu dung lượng tạm, write stalls |

### 3.1. Vì sao tombstone có thể cần được giữ?

Giả sử replica A đã xử lý DELETE, còn replica B mất kết nối và giữ bản ghi cũ. Nếu A bỏ mọi dấu xóa trước khi B được đồng bộ theo giao thức cần thiết, bản cũ có thể xuất hiện trở lại sau repair. Trong những hệ phù hợp, đây là nguy cơ **zombie data**.

Với Cassandra, các điều kiện **repair, replica và thời gian giữ tombstone** là một phần của an toàn dữ liệu. **Không tự rút ngắn gc_grace_seconds hoặc ép compaction** chỉ để lấy lại đĩa nhanh mà chưa hiểu trạng thái replica và chính sách repair.

### 3.2. Tombstone có thể làm truy vấn chậm

Một scan cần trả 100 bản ghi sống nhưng vùng dữ liệu chứa hàng triệu dấu xóa có thể phải xử lý lượng lớn entry trước khi có đủ kết quả. Số bản ghi **trả về ít** không đồng nghĩa số entry **đã đọc ít**.

Khi đo đọc bị chậm, xem thêm **tombstone scans, SSTables/files touched, bytes scanned và p99** thay vì chỉ nhìn query result count.

### 3.3. Xóa từng row khác xóa nguyên partition/segment

Nếu các bản ghi có thời hạn tương tự và công nghệ hỗ trợ **xóa nguyên đơn vị lưu trữ**, việc chia theo ngày/tuần rồi bỏ toàn bộ segment có thể hiệu quả hơn xóa từng row:

~~~~text
events_20261001 -> hết retention -> loại nguyên đơn vị
events_20261002 -> hết retention -> loại nguyên đơn vị
events_20261003 -> còn retention
~~~~

Nhưng **logical partition key** không nhất thiết tương ứng với **một file độc lập có thể drop**. Cassandra, DynamoDB, HBase, MongoDB và segment store có mô hình khác nhau. Cần kiểm chứng:

- Công nghệ có hỗ trợ drop time partition/segment thực sự không?
- Một partition có chứa bản ghi chưa được phép xóa không?
- Late events và cập nhật vào bucket cũ được xử lý thế nào?
- Snapshot, index và replica có giữ lại file?
- Query qua nhiều bucket có tăng fan-out không?

## 4. Cơ chế thu hồi theo một số họ NoSQL

| Engine/họ công nghệ | Cơ chế thường gặp | Nhóm chỉ số cần tập trung |
| --- | --- | --- |
| **Cassandra** | TTL/tombstone, SSTable compaction, repair và replica | Compaction pending, tombstone, read latency, disk growth |
| **HBase** | Cell TTL/versions, delete marker, HFile compaction | Region/StoreFile, HDFS I/O, compaction backlog |
| **RocksDB/LSM** | Delete markers và compaction theo level/strategy | Compaction bytes, pending bytes, write stalls |
| **MongoDB** | TTL monitor xóa document; storage engine tái sử dụng không gian | TTL deletes, reusable bytes, index/storage stats |
| **DynamoDB** | TTL item dựa vào epoch giây, xóa bất đồng bộ | Tuổi item hết hạn, deletion lag, stream/replica |
| **Redis** | Passive/active expiration; eviction riêng khi thiếu RAM | expired_keys, evicted_keys, memory/fragmentation |
| **Search/segment store** | Deleted document markers và segment merge | Merge I/O, deleted-doc ratio, segment count |

### 4.1. Cassandra

Ví dụ CQL trên một bảng đã được khai báo phù hợp:

~~~~sql
INSERT INTO telemetry.events_by_device (
    device_id, day_bucket, event_time, event_id, temperature
) VALUES (
    'device-42',
    '2026-11-14',
    '2026-11-14T08:00:00Z',
    550e8400-e29b-41d4-a716-446655440000,
    24.3
) USING TTL 2592000;
~~~~

TTL 2.592.000 giây bằng 30 ngày. Dữ liệu hết hiệu lực không đồng nghĩa SSTable lập tức biến mất. Compaction và an toàn xóa khi có replica/repair ảnh hưởng thời điểm loại phiên bản/tombstone.

Workload time-series có TTL tương đối đồng đều có thể phù hợp với một chiến lược compaction theo thời gian, nhưng cần xét **late writes, cập nhật dữ liệu cũ, kích thước cửa sổ và số replica**. Không coi một chiến lược là nhanh nhất ở mọi workload.

### 4.2. HBase

HBase có cell version và cấu hình TTL theo column family; ví dụ minh họa:

~~~~ruby
create 'sensor_history',
       { NAME => 'm', TTL => 2592000, VERSIONS => 1 }
~~~~

Delete marker, cell version và HFile có thể còn cho tới khi compaction đáp ứng điều kiện. Theo dõi **StoreFile count, region compaction queue, read latency, HDFS I/O** và tác động khi region split/balance.

**Cell timestamp** không mặc nhiên bằng thời điểm sự kiện nghiệp vụ; phải xác định deadline dùng loại timestamp nào trước khi áp dụng retention.

### 4.3. MongoDB

Một TTL index theo hạn tuyệt đối:

~~~~javascript
db.events.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
~~~~

expiresAt cần có kiểu thời gian mà TTL monitor nhận diện, thường là **BSON Date**. Bộ dọn nền có thể xóa **sau deadline**, không cam kết đúng từng giây. Thao tác xóa còn tác động tới index và replication.

Sau khi xóa, engine có thể giữ vùng trống để **tái sử dụng**; file size trên filesystem không nhất thiết giảm. Kiểm tra **reusable free space, allocated storage, index size và actual disk headroom** trước khi chạy compact/rebuild.

### 4.4. DynamoDB

DynamoDB TTL sử dụng thuộc tính hết hạn dạng **Unix epoch giây**. Item có thể còn hiển thị trong một khoảng thời gian sau khi hết hạn cho tới khi dịch vụ xóa bất đồng bộ. Nếu không được trả item quá hạn, query hoặc tầng ứng dụng phải kiểm tra deadline.

Không giả định chi phí xóa, độ trễ hoặc tác động đến stream/global replica giống MongoDB hay Cassandra; cần đối chiếu cấu hình dịch vụ đang chạy.

### 4.5. Redis

~~~~redis
SET cache:product:P-42 "{\"priceMinor\":1390000}" EX 300
TTL cache:product:P-42
INFO stats
INFO memory
~~~~

Key có thể hết hạn sau TTL, nhưng cũng có thể **bị eviction sớm** nếu thiếu bộ nhớ và policy cho phép. expired_keys và evicted_keys phản ánh hai nguyên nhân khác nhau; Redis memory allocator không có cùng cách thu hồi như SSTable compaction.

## 5. Chỉ số đo chi phí thu hồi

### 5.1. Reclaim lag

Định nghĩa:

\[
L_{\text{reclaim}} = t_{\text{reclaimed}} - t_{\text{eligible}}
\]

Trong đó **eligible** là thời điểm dữ liệu đủ điều kiện dọn theo retention và an toàn bản sao; **reclaimed** là lúc không gian được thu hồi theo **tầng đã chọn**. Đừng dùng hai mốc của hai đồng hồ không đồng bộ để kết luận chính xác đến mili giây.

Nên đo **p50/p95/p99 reclaim lag**, **tuổi dữ liệu cũ nhất đang chờ** và **số byte đang chờ thu hồi**. Một số file kẹt rất lâu có thể bị trung bình che lấp.

### 5.2. Reclaim throughput

\[
R_{\text{reclaim}} =
\frac{\Delta B_{\text{actually reclaimed}}}{\Delta t}
\]

Ví dụ thu hồi thực **120 GiB trong hai giờ** là **60 GiB/giờ**, tương đương khoảng **17,1 MiB/giây**. Không dùng tổng byte “đã gửi lệnh DELETE” làm byte thu hồi nếu file chưa được giải phóng.

### 5.3. Reclaim efficiency

\[
E_{\text{reclaim}} =
\frac{B_{\text{reclaimed}}}{B_{\text{processed}}}
\]

Giả sử compaction đọc **500 GiB input** và loại **50 GiB obsolete**, efficiency là **10%** nếu chọn input bytes làm mẫu số. Lượt compaction vẫn có thể hữu ích cho giảm số file/read amplification, nên không chỉ nhìn tỷ lệ này để đánh giá đúng/sai.

### 5.4. I/O cost per GiB reclaimed

\[
C_{\text{IO/reclaim}} =
\frac{B_{\text{background read}}+B_{\text{background write}}}
{B_{\text{reclaimed}}}
\]

Ví dụ:

~~~~text
Compaction read:        800 GiB
Compaction write:       500 GiB
Physical reclaimed:     100 GiB

Cost = (800 + 500) / 100
     = 13 GiB I/O cho mỗi 1 GiB thu hồi
~~~~

Đây là chỉ số **hiệu quả I/O thu hồi**, **không phải** định nghĩa đầy đủ của write amplification.

### 5.5. Write amplification

Một quy ước thực hành:

\[
WA =
\frac{B_{\text{physical writes attributed to workload}}}
{B_{\text{logical user writes}}}
\]

Phải nói rõ physical writes gồm WAL, index, replica, compaction và các tầng storage nào. Nếu hệ thống chỉ xuất **compaction writes / ingested bytes**, đó là **một thành phần WA**, không phải WA toàn hệ.

Ví dụ, logical user writes 200 GiB, compaction writes 600 GiB. Chỉ xét hai phần, hệ thống ghi 800 GiB, gấp **4 lần** input logic. Con số này chưa bao gồm mọi loại ghi khác.

### 5.6. Storage amplification

\[
SA =
\frac{B_{\text{occupied physical storage}}}
{B_{\text{logical live data}}}
\]

Nếu dữ liệu live 300 GiB, local file/index/obsolete chiếm 600 GiB thì SA = **2** theo phạm vi local. Nếu tính ở toàn cụm, cần ghi rõ có bao gồm các replica hay không.

### 5.7. Tốc độ tăng backlog

\[
G_{\text{backlog}} =
R_{\text{new work}} - R_{\text{completed work}}
\]

Nếu tạo 800 GiB maintenance work mỗi ngày, chỉ xử lý 600 GiB thì backlog tăng **200 GiB/ngày** theo mô hình đo tương đương. Một cấu hình bền vững cần năng lực dọn **trung bình dài hạn** theo kịp tốc độ tạo công việc.

## 6. Tác vụ nền tác động tới API như thế nào?

~~~~text
                   Node tài nguyên hữu hạn
                 ┌───────────────────────┐
API đọc ---------│ CPU / RAM / SSD I/O   │
API ghi ---------│ Network / queues      │ ---> p50 / p95 / p99
Compaction ------│                       │
TTL cleanup -----│                       │
Repair/backup ---│                       │
                 └───────────────────────┘
~~~~

Các đường tranh chấp:

- **I/O:** background merge đọc/ghi file lớn, tăng disk queue và đuôi độ trễ.
- **CPU:** nén, giải nén, merge khóa, checksum, garbage collection.
- **RAM:** compaction buffers cạnh tranh với cache/memtable.
- **Mạng:** repair, rebalance và replication tranh bandwidth.
- **Dung lượng tạm:** output được ghi trước khi input cũ bị xóa.
- **Giới hạn concurrency:** write stall hoặc lock/latch tùy engine.

### 6.1. p99 phản ánh tác động rõ hơn throughput trung bình

| Trạng thái giả định | Throughput xử lý | p50 ghi | p99 ghi | Timeout |
| --- | ---: | ---: | ---: | ---: |
| Bình thường | 10.000 req/s | 8 ms | 45 ms | 0,01% |
| Compaction vừa | 9.900 req/s | 10 ms | 110 ms | 0,10% |
| Compaction backlog lớn | 9.300 req/s | 14 ms | 480 ms | 2,50% |

**Số liệu hoàn toàn minh họa.** Throughput trung bình có thể gần như giữ nguyên trong khi tail latency và timeout vượt SLO. Phải đo **offered vs achieved throughput**, p95/p99 và lỗi, không chỉ số lệnh thành công.

### 6.2. Backlog kéo dài có thể gây write stall

Một số LSM engine giới hạn ghi khi pending compaction bytes, file count hoặc level pressure vượt ngưỡng. Ví dụ:

~~~~text
New compaction work:    450 GiB/ngày
Completed work:         300 GiB/ngày
Growth:                 150 GiB/ngày
After 7 days:         1.050 GiB backlog tăng thêm
~~~~

Giảm compaction có thể làm p99 đẹp hơn trong 30 phút đầu nhưng dẫn tới đầy đĩa hoặc write stall sau vài ngày. Thử nghiệm phải chạy **đủ dài** để thấy xu hướng công việc tồn đọng.

### 6.3. CPU thấp không có nghĩa hệ thống còn dư công suất

Một node chỉ dùng 40% CPU vẫn có thể chậm nếu SSD bị giới hạn IOPS, throughput hoặc latency. Tương tự network quota hoặc volume credit có thể cạn trước CPU.

Cần đo đồng thời **CPU, RAM, disk read/write, queue depth, I/O latency, network, p99** và hoạt động nền theo từng node/shard.

## 7. Dung lượng tạm và headroom

Nếu compaction cần ghi **output file** trước khi bỏ input, quá trình dọn có thể cần thêm dung lượng ngay lúc đĩa đã gần đầy.

~~~~text
Input files:       600 GiB
Live output:       500 GiB
Obsolete data:     100 GiB
Output phải được ghi trước khi xóa file cũ trong kịch bản này
~~~~

Không phải engine nào cũng cần đồng thời thêm 500 GiB vì có thể xử lý file theo nhóm nhỏ và xóa dần. Nhưng **không được giả định** “thu hồi 100 GiB” luôn chạy được khi chỉ còn vài GiB trống.

Một khung dự trù:

\[
H_{\text{required}} =
H_{\text{ingest burst}} +
H_{\text{maintenance peak}} +
H_{\text{recovery}} +
H_{\text{safety}}
\]

Các phần có thể không đạt đỉnh cùng thời điểm; nên đo **peak simultaneous occupancy** trong thử nghiệm thay vì cộng máy móc.

### 7.1. Snapshot có thể giữ file đã không còn dùng cho query

~~~~text
SSTable cũ ------> Snapshot A còn tham chiếu
      |
Compaction tạo SSTable mới
      |
Query thông thường không cần SSTable cũ
      |
File cũ vẫn không thể xóa vì snapshot
~~~~

Cần tính snapshot retention, backup incremental, dung lượng unique, WAL retention và những bản sao ở object storage. Giảm retention của dữ liệu chính **không tự giảm hóa đơn backup** nếu backup vẫn giữ bản lịch sử.

## 8. Mô hình chi phí: từ lưu lượng đến dung lượng và I/O

Giả sử **50 triệu sự kiện/ngày**, payload **1 KiB/sự kiện**, giữ nóng **30 ngày**, replication factor **3**.

### 8.1. Payload logic

\[
B_{\text{daily}}
=50.000.000\times1.024
=51.200.000.000\text{ byte}
\]

Tương đương khoảng **47,68 GiB/ngày**.

Trong 30 ngày:

\[
47,68\times30 \approx 1.430,4\text{ GiB}
\approx1,40\text{ TiB}
\]

Nhân ba bản sao, **chỉ payload trước nén/overhead** khoảng **4,19 TiB**. Đây không phải disk footprint thực vì còn index, key, metadata, nén, tombstone, WAL, file tạm, snapshot và chênh lệch phân bố.

### 8.2. Nếu thu hồi chậm ba ngày

\[
47,68\text{ GiB/ngày}\times3\text{ ngày}
\approx143,04\text{ GiB logic tồn đọng}
\]

Nếu ba replica có tình trạng tương tự, thêm khoảng **429,12 GiB replicated payload**, chưa tính overhead. Đây là cách ước lượng tác động dung lượng của **reclaim lag** trong trạng thái ổn định.

### 8.3. Chi phí I/O của một đợt dọn

Giả sử trong 2 giờ compaction đọc **800 GiB**, ghi **500 GiB**, thu hồi **100 GiB**.

\[
B_{\text{IO}}=800+500=1.300\text{ GiB}
\]

\[
\text{I/O trung bình} =
\frac{1.300\times1.024}{7.200}
\approx184,9\text{ MiB/s}
\]

I/O cost là **13 GiB I/O/1 GiB reclaimed**. Nếu thiết bị chỉ còn khoảng 200 MiB/s băng thông an toàn cho toàn workload, maintenance có thể cạnh tranh mạnh với API. **Không suy ra p99 trực tiếp** từ mức I/O trung bình: phải đo độ trễ cùng thời gian.

### 8.4. Tổng chi phí tiền và vận hành

\[
C_{\text{total}} =
C_{\text{storage}}+
C_{\text{I/O}}+
C_{\text{compute}}+
C_{\text{network}}+
C_{\text{backup}}+
C_{\text{operational}}
\]

Chi phí có thể bao gồm GiB-tháng, IOPS/throughput, node giờ, cross-region transfer, backup retention và công xử lý sự cố. Mỗi dịch vụ có cách tính phí khác nhau; không mặc định TTL hoặc DELETE có chi phí bằng nhau trên mọi NoSQL.

## 9. Tối ưu retention từ thiết kế dữ liệu

### 9.1. Gom dữ liệu cùng thời hạn

Với time-series và dữ liệu có vòng đời đồng đều, có thể phân theo ngày/tuần nếu công nghệ hỗ trợ dọn nguyên đơn vị. Tuy nhiên phải cân nhắc:

| Bucket | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Theo giờ | Hết hạn sát mốc, mỗi lần dọn nhỏ | Rất nhiều partition, fan-out đọc |
| Theo ngày | Cân bằng quản lý và kích thước | Ngày nóng có thể rất lớn |
| Theo tháng | Ít đơn vị lưu | Mỗi lần dọn lớn, giữ dữ liệu quá hạn lâu nếu chỉ drop nguyên tháng |
| Theo hash key | Phân tán ghi | Khó xóa theo thời gian |
| Thời gian + hash | Kiểm soát tuổi và phân tải | Đọc nhiều bucket, tăng complexity |

Nếu retention yêu cầu chính xác tới phút nhưng dọn file theo ngày, đường đọc phải **không trả dữ liệu đã quá deadline** và chính sách xóa vật lý phải đáp ứng giới hạn được phép.

### 9.2. Dữ liệu đến muộn

Một sensor ghi sự kiện ngày 10 nhưng gửi tới ngày 12. Nếu retention lấy theo **eventTime**, bản ghi có thể chỉ còn 28 ngày kể từ ngày nhận. Nếu retention lấy theo **serverAcceptedAt**, nó có thể còn đủ 30 ngày sau khi nhận.

Phải xác định:

- Deadline tính theo eventTime hay ingestionTime?
- Dữ liệu quá hạn ngay lúc tới được bỏ hay lưu ở kho lạnh?
- Có cập nhật file/bucket cũ làm tăng compaction không?
- Read model và báo cáo lịch sử có cần tính lại không?

Không để một field timestamp từ client không đáng tin âm thầm quyết định việc giữ/xóa dữ liệu quan trọng.

### 9.3. Không thêm jitter vượt thời hạn bắt buộc

Phân tán deadline có thể giảm các đợt hết hạn đồng loạt trong **cache có giới hạn linh hoạt**. Nhưng với dữ liệu có yêu cầu xóa trước mốc pháp lý/bảo mật, không được kéo dài TTL vượt deadline vì muốn giảm tải.

Thay vào đó, xem xét cách chia file, capacity, lịch dọn và đường kiểm tra hạn logic để giữ tính đúng.

## 10. Điều chỉnh tác vụ nền: cân bằng p99 với backlog

Các lựa chọn tùy engine:

- Compaction strategy theo size/level/time window.
- Số compaction job/thread đồng thời.
- Giới hạn I/O hoặc throttle nền.
- Kích thước flush/memtable và compaction input.
- Lịch repair, snapshot, rebalance và index rebuild.
- Batch size và concurrency của job DELETE ứng dụng.
- Mở rộng node/disk/headroom khi đã tới giới hạn.

### 10.1. Throttle là đánh đổi, không phải xóa chi phí

~~~~text
Phát sinh compaction work:  400 GiB/ngày
Xử lý trước throttle:      450 GiB/ngày
=> backlog có cơ hội giảm

Xử lý sau throttle:        250 GiB/ngày
=> backlog tăng ~150 GiB/ngày
~~~~

Nếu throttle để p99 tốt hơn giờ cao điểm, phải có lịch/công suất **xử lý bù ngoài đỉnh** và kiểm chứng rằng tốc độ trung bình dài hạn đủ. Một hệ 24/7 có thể phù hợp với throttle liên tục hơn chạy một đợt rất lớn vào ban đêm.

### 10.2. Tăng concurrency có thể làm chậm API

Nhiều worker compaction giúp giải quyết backlog nếu tài nguyên còn dư. Khi SSD/CPU bão hòa, tăng worker có thể:

- Tăng I/O queue, tail latency.
- Làm giảm page cache hữu ích.
- Tiêu tốn thêm dung lượng file tạm.
- Gây đụng nhau với repair/rebalance.

Chọn concurrency bằng đồ thị **reclaim throughput, p99, error và backlog**, không chỉ dựa vào số CPU core.

### 10.3. Tránh thao tác nặng trên production mà chưa có phương án

Major/force compaction, compact/vacuum, reindex hoặc rebuild lớn có thể tốn I/O và dung lượng tạm. Trước khi thực hiện cần biết điều kiện an toàn của engine, backup, rollback, giới hạn lưu trữ và tác động tới API. **Không chạy force compaction như phản xạ đầu tiên khi đĩa đang tăng**.

## 11. Dashboard giám sát vòng đời

Ba nhóm chỉ số phải được đặt cùng trục thời gian:

| Nhóm | Chỉ số | Câu hỏi |
| --- | --- | --- |
| **Dung lượng** | live/obsolete/reusable/physical bytes, index/WAL, snapshot bytes | Dữ liệu nằm ở đâu? |
| **Maintenance** | compaction read/write bytes, pending queue, reclaim lag, repair progress | Công việc nền có theo kịp không? |
| **Ứng dụng** | offered/achieved RPS, p50/p95/p99, lỗi, timeout, retry | Người dùng chịu ảnh hưởng gì? |

Bổ sung **disk IOPS/throughput/latency/queue, CPU/RAM/GC, network, số node/shard nóng nhất** và chi phí. Một node bị đầy trước toàn cụm có thể gây sự cố dù disk used trung bình còn thấp.

Tên metric cụ thể khác theo phiên bản và exporter: Cassandra có compaction/SSTable/repair metrics; HBase có region/StoreFile/compaction; RocksDB có pending bytes và stall; MongoDB có TTL/storage/index; Redis có expired_keys/evicted_keys/memory. Cần xác minh **đơn vị và phạm vi** của mỗi counter trước khi tính tỷ lệ.

### 11.1. Tương quan không tự chứng minh nguyên nhân

~~~~text
Time           10:00    10:15    10:30    10:45
Compaction I/O  thấp      cao      cao     giảm
Disk queue     thấp      cao      cao      vừa
p99 API ghi     45ms     190ms    260ms     90ms
~~~~

Các biểu đồ biến đổi cùng nhau là một dấu hiệu, nhưng có thể traffic khách hàng cũng tăng. Cần **đối chứng cùng offered workload** hoặc lặp thử nghiệm để xác định tác động nhân quả.

### 11.2. Dự báo thời gian hết dung lượng

\[
T_{\text{to-full}} \approx
\frac{B_{\text{usable free}}}{R_{\text{net physical growth}}}
\]

Chỉ có ý nghĩa khi tốc độ tăng vật lý **dương** và cửa sổ đo đại diện. Compaction có thể giải phóng file theo đợt, ingest có thể burst; phải xem headroom và thay đổi tải thay vì tin một dự báo tuyến tính.

## 12. Thử nghiệm thu hồi và ảnh hưởng nền

Benchmark chỉ ghi dữ liệu mới trong 5 phút **không** đại diện cho retention 30 ngày. Cần dữ liệu nhiều tuổi, file ở nhiều mức, snapshot và dấu xóa. Có thể tạo dataset lịch sử bằng API/công cụ được engine hỗ trợ; **không chỉnh đồng hồ máy chủ tùy tiện** chỉ để ép TTL nhanh vì sẽ ảnh hưởng replication và hệ khác.

### 12.1. Năm giai đoạn

1. **Baseline:** ổn định workload, đo p99, throughput và tác vụ nền bình thường.
2. **Chuẩn bị obsolete data:** tạo lượng dữ liệu cũ/hết hạn đã biết.
3. **Reclaim phase:** tiếp tục cùng tải API khi dọn/compaction.
4. **Post-reclaim:** quan sát bytes thu hồi, queue và p99 sau khi ổn định.
5. **Lặp lại:** ghi version, topology, index, replica, loại đĩa, consistency và kết quả nhiều vòng.

### 12.2. Ma trận thí nghiệm

| Kịch bản | Thay đổi | Điều cần đo |
| --- | --- | --- |
| Baseline | Ghi/đọc và maintenance bình thường | p99, background steady state |
| TTL wave | Nhiều record hết hạn gần nhau | Cleanup peak, reclaim lag, API |
| TTL phân tán | Deadline được phân bố hợp lệ | So sánh đỉnh I/O và tail latency |
| Sparse deletes | Xóa 10% record xen kẽ dữ liệu sống | Tombstone, bytes scan, reclaim efficiency |
| Time partition | Drop đơn vị khi engine hỗ trợ | Chi phí dọn, đọc nhiều bucket |
| Churn cao | Cập nhật/xóa nhiều phiên bản cùng key | WA, SSTables/index và p99 |
| Snapshot held | Snapshot vẫn giữ input file | Reusable vs physically freed |
| Overlap | Compaction + repair + backup | CPU/I/O/network contention |
| Data growth | 1×, 5×, 10× dung lượng | Queue, index pressure, headroom |
| Failure | Mất node/region ở môi trường test | Repair, recovery, tính đúng |

Ví dụ đặc tả workload:

~~~~yaml
experiment: reclaim-background-impact
dataset:
  eventsPerDay: 50000000
  avgPayloadBytes: 1024
  retentionDays: 30
  replicationFactor: 3
  hotDeviceSharePercent: 20
workload:
  peakWritesPerSecond: 12000
  readsPerSecond: 24000
  queries:
    - point_lookup
    - latest_100_by_device
    - range_last_24h
    - range_last_30d
maintenance:
  scenarios:
    - baseline
    - expiration_wave
    - sparse_deletes
    - time_partition_if_supported
    - snapshot_held
    - repair_overlap
measure:
  - live_expired_reusable_physical_bytes
  - reclaimed_bytes_per_hour
  - reclaim_lag_p95_p99
  - background_read_write_bytes
  - pending_compaction_bytes
  - disk_IOPS_latency_queue
  - API_p50_p95_p99_errors
  - offered_vs_achieved_RPS
  - data_correctness_and_recovery
~~~~

Đây là **mẫu đặc tả**, không phải cấu hình benchmark chạy trực tiếp. Chọn SLO, engine/driver, node, index, replica và cách xuất metric theo môi trường thực.

### 12.3. Kết quả minh họa

| Kịch bản | Reclaimed | I/O nền | p99 ghi | p99 đọc | Backlog |
| --- | ---: | ---: | ---: | ---: | --- |
| Bình thường | 40 GiB/h | 300 GiB/h | 65 ms | 45 ms | Ổn định |
| Xóa rải rác theo row | 25 GiB/h | 700 GiB/h | 170 ms | 140 ms | Tăng |
| Drop time segment hợp lệ | 90 GiB/h | 180 GiB/h | 75 ms | 55 ms | Giảm |
| Throttle mạnh | 12 GiB/h | 120 GiB/h | 55 ms | 50 ms | Tăng nhanh |
| Tăng concurrency | 80 GiB/h | 950 GiB/h | 310 ms | 260 ms | Giảm |

**Tất cả số liệu giả định.** Không chọn throttle mạnh chỉ vì p99 đẹp nếu backlog còn tăng; cũng không chọn concurrency cao nhất nếu vi phạm SLO. Phương án tốt phải thỏa mãn **retention logic, reclaim lâu dài, p99, headroom, an toàn replica và tổng chi phí**.

## 13. Kiểm chứng tính đúng sau cleanup

Thử nghiệm không chỉ đo số GiB, còn phải khẳng định:

1. Dữ liệu **chưa hết hạn** vẫn đọc được.
2. Dữ liệu **đã hết hạn** không xuất hiện ở đường đọc theo retention.
3. Dữ liệu xóa không hồi sinh sau khi replica cũ quay lại.
4. Index/read model tôn trọng trạng thái xóa theo ngân sách freshness.
5. Dữ liệu đến muộn được xử lý theo eventTime/ingestionTime đã định.
6. Snapshot/restore và repair vẫn hoạt động theo RPO/RTO.
7. Counter/rollup không vô tình đếm trùng dữ liệu đã loại.
8. Batch cleanup và compaction không khiến API treo không đo được.

Một phép thử quan trọng:

~~~~text
Replica A đã nhận DELETE event-42.
Replica B mất kết nối, còn event-42 cũ.
Trong thời gian B offline, A thực hiện compaction.
B trở lại và tham gia repair/đồng bộ.
~~~~

Kết quả phải phù hợp với cơ chế giữ tombstone/repair của engine. Không dùng môi trường production để mô phỏng lỗi phá hoại này khi chưa có kiểm soát.

### 13.1. Kiểm tra backup/restore

Restore từ snapshot cũ có thể mang lại dữ liệu đã từng bị xóa. Cần xác định có phải replay delete events, đối soát retention mới hoặc chặn trả dữ liệu trước khi phục vụ API. **RPO/RTO và chính sách xóa dữ liệu** là hai hợp đồng khác nhau, phải kiểm chứng cùng nhau.

## 14. Runbook khi TTL đã bật nhưng đĩa vẫn tăng

**Bước 1 — Xác minh hạn dùng:** Có đặt TTL đúng record không, có nhầm giây/mili giây không, field đúng kiểu không, cập nhật có làm mất TTL không, dữ liệu lịch sử có được backfill hay không?

**Bước 2 — Phân tách dung lượng:** Đo live, expired, obsolete, reusable, physical, index, WAL, snapshot và sự phân bố theo node. Đừng chỉ nhìn tổng disk used.

**Bước 3 — Tìm nghẽn nền:** Pending compaction tăng hay giảm, throughput dọn so với công việc mới, I/O queue, RAM/CPU/network, snapshot còn giữ file và replica/repair có chậm không?

**Bước 4 — Giảm rủi ro:** Tạm hoãn job không bắt buộc, bổ sung headroom nếu cần, phân lịch maintenance, chỉnh throttle có kiểm soát, sửa repair/backup/snapshot bị kẹt. Chỉ force compact/rebuild khi hiểu chi phí và có phương án phục hồi.

**Bước 5 — Xác nhận:** Backlog không tăng lại dưới tải thật, disk growth về mức có thể dự báo, p99 đạt SLO, dữ liệu không bị xóa nhầm và backup/replica vẫn đúng.

## 15. Những nhầm lẫn cần tránh

1. **DELETE thành công tức đã trả dung lượng đĩa.** Sai: nhiều hệ mới thay trạng thái logic.
2. **TTL hết hạn là file lập tức biến mất.** Không bảo đảm.
3. **File size không giảm tức chưa dọn.** Vùng trống có thể được tái sử dụng.
4. **Thu hồi 100 GiB chỉ tốn 100 GiB I/O.** Có thể phải đọc/ghi lượng live data lớn hơn.
5. **Compaction chạy nền không ảnh hưởng API.** Nó tranh CPU, I/O, RAM và mạng.
6. **Tắt compaction giúp latency tốt mãi.** Backlog/write stalls có thể tăng.
7. **Càng nhiều compaction worker càng tốt.** Có thể bão hòa đĩa và tăng p99.
8. **Partition theo ngày là file theo ngày có thể drop.** Phụ thuộc engine.
9. **Dọn tombstone sớm càng an toàn.** Có thể gây hồi sinh dữ liệu khi replica trễ.
10. **Giảm retention là hóa đơn giảm ngay.** Snapshot, file reuse và billing model có độ trễ khác.
11. **Disk used (%) là đủ.** Còn lag, backlog, WA, headroom và p99.
12. **Throughput trung bình ổn là không có ảnh hưởng.** Tail latency và lỗi có thể xấu.
13. **Xóa hàng loạt nửa đêm chắc chắn nhẹ.** Backup/repair có thể cùng diễn ra.
14. **Không còn pending compaction là mọi bản sao đã xóa.** Backup/read model có vòng đời riêng.

## 16. Bài tập tình huống: hệ thống nhật ký IoT

Một nền tảng IoT có:

- 100.000 thiết bị, tạo **60 triệu sự kiện/ngày**.
- Payload trung bình **0,8 KiB** trước nén/index.
- Replication factor **3**, retention nóng **14 ngày**.
- API đọc **100 sự kiện mới nhất** và **lịch sử 24 giờ**.
- p99 đọc mục tiêu **dưới 150 ms**, p99 ghi **dưới 200 ms**.
- Giờ cao điểm 3 lần bình thường; 5% dữ liệu đến trễ tới 12 giờ.

Sau một tuần:

~~~~text
TTL đã được cấu hình.
Expired document/row count tăng.
Disk used: 72% -> 83%.
Compaction backlog tăng liên tục.
p99 ghi cao điểm: 90 ms -> 320 ms.
Snapshot hàng ngày, giữ 14 bản.
~~~~

### Phần A — Dung lượng

Tính payload thô mỗi ngày, cho 14 ngày, rồi nhân 3 replica. Nêu phần chưa tính: compression, index, metadata, WAL, tombstone, snapshot, compaction temp. Giải thích vì sao **83% disk used** chưa xác định được nơi giữ dữ liệu.

### Phần B — Chi phí đợt reclaim

~~~~text
Compaction read:        750 GiB
Compaction write:       600 GiB
Actually reclaimed:     150 GiB
Duration:                3 giờ
~~~~

Hãy tính reclaim throughput, I/O cost/GiB reclaimed và I/O trung bình MiB/s. **Gợi ý:** 150/3 = **50 GiB/h**; (750+600)/150 = **9 GiB I/O/GiB reclaimed**; (1350×1024)/(3×3600) ≈ **128 MiB/s**.

### Phần C — Chọn chiến lược retention

So sánh TTL từng record, drop time segment khi engine hỗ trợ và giữ raw 3 ngày + rollup theo giờ thêm 14 ngày. Phân tích tác động tới query 24 giờ, late events, deadline, index, backup và chi phí thu hồi.

### Phần D — Backlog

Nếu tạo thêm **350 GiB công việc/ngày** nhưng chỉ xử lý **250 GiB**, sau 7 ngày backlog tăng bao nhiêu? Làm gì để năng lực dọn dài hạn theo kịp mà vẫn giữ p99 trong SLO?

### Phần E — Benchmark

Thiết kế các bài thử baseline, TTL wave, sparse deletes, time partition, snapshot-held, burst 3× và repair overlap. Báo cáo **reclaimed bytes, reclaim lag, background I/O, p99, headroom, backlog và correctness** cho mỗi bài.

### Hướng giải

Nhóm vận hành có thể cần thay bố cục retention, giảm xóa rải rác nếu engine cho phép, tăng headroom, điều chỉnh lịch nền và vòng đời snapshot. Nhưng trước khi thay đổi phải **đo cơ chế thu hồi thực tế và bảo đảm an toàn repair/replica**. Không có một thao tác force compaction nào thay thế được kế hoạch vòng đời dữ liệu có thể kiểm chứng.

**Kết luận:** Trong NoSQL, **hết hạn logic, xóa vật lý, tái sử dụng không gian và giảm chi phí là những mốc khác nhau**. Để đánh giá retention, hãy đo đồng thời **dung lượng thực thu hồi, reclaim lag, I/O/CPU bảo trì, backlog, headroom và p99 ứng dụng**. Vận hành bền vững đòi hỏi **tốc độ dọn dài hạn theo kịp dữ liệu hết hiệu lực** mà không đánh đổi tính đúng, khả năng khôi phục hoặc SLO.
