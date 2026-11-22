# Độ trễ đọc/ghi và phân vị thay vì chỉ giá trị trung bình trong Apache Cassandra

## 1. Vì sao “độ trễ trung bình tốt” chưa đủ?

Apache Cassandra là hệ quản trị dữ liệu phân tán **wide-column**. Ứng dụng định tuyến thao tác theo **partition key**, phục vụ truy vấn bằng bảng thiết kế theo access pattern và chọn **consistency level** để điều phối việc đọc/ghi giữa các replica. Một thao tác CQL có thể trải qua Java Driver, network, coordinator, replica, memtable, SSTable, compaction hoặc hoạt động repair đang chạy.

Một dashboard chỉ hiển thị **average read latency = 100 ms** chưa trả lời được câu hỏi quan trọng: *Có bao nhiêu người dùng đang phải chờ vài giây?*

Xét hai nhóm, mỗi nhóm có đúng 1.000 request đọc:

| Phân bố độ trễ | Nhóm A | Nhóm B |
|---|---:|---:|
| Request hoàn thành trong 50 ms | 0 | 980 |
| Request hoàn thành trong 100 ms | 1.000 | 0 |
| Request hoàn thành trong 2.550 ms | 0 | 20 |
| **Trung bình** | **100 ms** | **100 ms** |
| **p50** | **100 ms** | **50 ms** |
| **p95** | **100 ms** | **50 ms** |
| **p99** (nearest-rank) | **100 ms** | **2.550 ms** |

Cả hai nhóm có **cùng giá trị trung bình**:

~~~text
A: 1.000 × 100 ms / 1.000 = 100 ms

B: (980 × 50 ms + 20 × 2.550 ms) / 1.000
 = (49.000 + 51.000) / 1.000
 = 100 ms
~~~

Nhưng nhóm B có **2% request mất 2,55 giây**, trong khi nhóm A không request nào chậm hơn 100 ms. Nếu người dùng nhìn màn hình đợi một truy vấn đúng lúc rơi vào 2% đó, chỉ số average đẹp không có giá trị trấn an.

Đây là lý do quan sát Cassandra cần **độ trễ theo phân vị (percentile/quantile)**, đặc biệt **p50, p95, p99** và khi đủ mẫu có thể theo dõi **p99.9**, bên cạnh throughput, error rate và resource metrics.

## 2. Phân vị p50, p95, p99 thực sự có nghĩa gì?

### 2.1. Định nghĩa qua các request đã hoàn thành

- **p50 (median):** khoảng 50% request quan sát có latency không vượt giá trị này.
- **p95:** khoảng 95% request không vượt giá trị này; nhóm chậm nhất chiếm khoảng 5%.
- **p99:** khoảng 99% request không vượt giá trị này; nhóm chậm nhất chiếm khoảng 1%.
- **p99.9:** tập trung vào đuôi rất xa, nơi chỉ khoảng 0,1% request chậm hơn.

Trong một mẫu gồm `N` giá trị latency đã sắp tăng, cách tính minh họa *nearest-rank* chọn vị trí:

~~~text
vị trí pX = ceil((X / 100) × N)

Ví dụ N = 1.000:
p50: giá trị thứ 500
p95: giá trị thứ 950
p99: giá trị thứ 990
~~~

Thư viện metrics thường dùng histogram, bucket hoặc phương pháp nội suy/ước lượng khác; giá trị p99 có thể khác nhẹ so với nearest-rank. Vì vậy hãy giữ **phương pháp và độ phân giải nhất quán** khi so sánh trước/sau.

### 2.2. Percentile không phải “tỷ lệ thời gian hệ thống nhanh”

Nếu p99 = 200 ms trong cửa sổ đo, câu diễn giải đúng là khoảng **99% request quan sát được hoàn thành trong tối đa 200 ms**. Không có nghĩa 99% thời gian máy hoạt động ở trạng thái nhanh, cũng không có nghĩa xác suất cho mọi request tương lai được bảo đảm chính xác như vậy.

Một phân vị là **thống kê của tập mẫu trong một thời gian đo cụ thể**, chịu ảnh hưởng tải, thời điểm, mix truy vấn và phương pháp ghi nhận.

### 2.3. Số lượng mẫu quyết định mức tin cậy

Khi chỉ có 50 request trong năm phút, p99 gần như trùng với request chậm nhất; một biến động đơn lẻ khiến đồ thị giật mạnh. Với 100.000 request, khoảng 1.000 request thuộc nhóm chậm nhất 1%, cho phép điều tra ổn định hơn.

Đừng kết luận từ p99 của bảng ít traffic khi chưa xem:

1. Số request trong cửa sổ.
2. Độ dài cửa sổ tính (một phút, năm phút, một giờ).
3. Cách lấy mẫu và loại bỏ outlier.
4. Có tính request timeout/error hay không.
5. Histogram là số liệu **node, table, driver hay end-to-end**.

## 3. Độ trễ Cassandra có nhiều lớp khác nhau

Một request đọc có thể đi qua những thành phần sau:

~~~mermaid
flowchart TD
    U["Ứng dụng / HTTP API"] --> A["Java Driver: chọn node, connection, queue, retry"]
    A --> B["Mạng client → coordinator"]
    B --> C["Coordinator: định tuyến theo token và consistency level"]
    C --> D["Replica: memtable / cache / SSTable / tombstone"]
    D --> C
    C --> E["Đủ phản hồi theo read consistency"]
    E --> F["Mạng và driver trả dữ liệu"]
    F --> U
    G["Compaction, repair, GC, I/O và tải nền"] -. ảnh hưởng .-> D
    H["WAN giữa datacenter"] -. ảnh hưởng .-> C
~~~

Vì có nhiều lớp, cần phân biệt rõ **thời điểm bắt đầu và kết thúc đồng hồ đo**:

| Mức đo | Bao gồm | Không nhất thiết bao gồm |
|---|---|---|
| **Latency ở ứng dụng** | Từ lúc bắt đầu truy cập Cassandra đến khi ứng dụng nhận và xử lý kết quả theo phép đo | Các bước HTTP khác nếu không đo end-to-end |
| **Driver request latency** | Thời gian driver nhìn thấy request, có thể gồm chọn host, kết nối, request/retry và network theo loại metric | Toàn bộ logic nghiệp vụ trước/sau request |
| **Coordinator/proxy latency** | Xử lý request tại node điều phối và chờ phản hồi liên quan | Queue hoặc xử lý ngoài Cassandra phía client |
| **Table/replica local latency** | Hoạt động đọc/ghi phía storage engine trên node | Toàn bộ vòng đi mạng, coordinator và driver |
| **HTTP/API latency** | Toàn bộ thời gian phục vụ API, gồm business logic, Cassandra và hệ thống khác | Không tự chỉ ra Cassandra là nguyên nhân |

**Không so trực tiếp các chỉ số khác phạm vi.** Ví dụ application p99 = 900 ms và table-local p99 = 40 ms không phải mâu thuẫn: thời gian còn lại có thể nằm ở driver queue, coordinator, network, replica khác, retry hoặc hệ thống ngoài Cassandra.

Không thể lấy `p99(client) - p99(table)` để suy ra chính xác p99 của network. **Percentile không cộng hoặc trừ trực tiếp như các đại lượng tuyến tính**, do các phân vị có thể thuộc các request khác nhau.

## 4. Độ trễ đọc và ghi cần tách riêng

### 4.1. Đường đọc

Một truy vấn `SELECT` nhắm tới partition cụ thể có thể dùng key cache, Bloom filter, memtable, SSTable index và các chunk nén. Nếu một partition trải trên nhiều SSTable và có nhiều tombstone, replica có thể phải merge nhiều phiên bản hoặc quét nhiều row đã xóa trước khi trả số row còn sống.

Các yếu tố khiến **read latency** tăng:

- Thiếu partition key hoặc query dùng `ALLOW FILTERING` khiến phạm vi quét lớn.
- Partition cực rộng, clustering range không giới hạn.
- Nhiều SSTable chồng lấn, compaction không theo kịp.
- Nhiều tombstone hoặc dữ liệu TTL hết hạn trong phạm vi đọc.
- Disk I/O, cache hit thấp, decompression hoặc CPU/GC tăng.
- Replica chậm, network/WAN, hoặc coordinator phải chờ đủ read CL.
- Speculative read và các cơ chế đối chiếu/repair trên đường đọc (tùy phiên bản).

**Một `LIMIT 20` không đảm bảo thao tác đọc nhẹ**: Cassandra có thể quét qua nhiều tombstone mới tìm đủ 20 row sống.

### 4.2. Đường ghi

Ghi thông thường đi qua coordinator tới replica, sử dụng commit log và memtable tại các replica. Client được trả thành công sau khi thỏa điều kiện phản hồi của write consistency; việc flush SSTable và compaction là công việc nền, không phải mỗi lần ghi đều phải đợi compaction hoàn tất.

Những yếu tố khiến **write latency** tăng:

- Node đích chậm xác nhận do commit log/disk I/O hoặc áp lực memtable.
- Hàng đợi mutation, overload, CPU/GC hoặc backpressure.
- Replication CL yêu cầu nhiều replica; đặc biệt có thể cần WAN khi dùng `QUORUM`, `EACH_QUORUM` trong đa DC.
- Mutation hoặc batch quá lớn; update/deletion tăng write load và gánh nặng compaction về sau.
- Network lỗi/chậm, hinted handoff, streaming hoặc repair cạnh tranh tài nguyên.
- Với **LWT (IF / IF NOT EXISTS)**, các vòng đồng thuận Paxos có đường đi khác ghi thường và phải đo tách riêng.

Không kết luận “p99 ghi cao nghĩa là SSTable flush bị chậm” nếu chưa kiểm tra commit log, mutation stage, load, CL và node đích. **Ghi thường không nhất thiết đợi SSTable flush xong**.

### 4.3. Consistency level làm thay đổi đuôi latency

Ví dụ một keyspace `NetworkTopologyStrategy` có RF=3 trong DC cục bộ:

- `ONE` chỉ cần một replica xác nhận theo quy tắc của thao tác.
- `LOCAL_QUORUM` cần hai trong ba replica ở DC cục bộ.
- `ALL` cần mọi replica được yêu cầu.

Ở mức yêu cầu nhiều phản hồi hơn, request dễ bị ảnh hưởng bởi **replica chậm thứ k** trong tập cần thiết. Tuy nhiên không thể mặc định latency tăng tuyến tính với số ACK; coordinator có thể gửi request song song và nhiều tối ưu khác ảnh hưởng thời điểm kết thúc.

Trong nhiều DC, `EACH_QUORUM` áp dụng cho các thao tác ghi được hỗ trợ và cần quorum tại mỗi DC; nó có thể kéo đuôi latency theo DC chậm hoặc mạng WAN. `EACH_QUORUM` **không phải CL cho SELECT thông thường**.

## 5. Đọc đúng một biểu đồ percentile

Một dashboard có p50 = 8 ms, p95 = 45 ms, p99 = 900 ms cần được đọc theo thứ tự:

1. **Tập request nào?** Ghi hay đọc, bảng/operation nào, DC nào, từ node coordinator hay client?
2. **Cửa sổ thời gian và số mẫu?** Một phút có 500 request hay 50.000 request?
3. **Mức độ chênh lệch?** p99/p50 lớn cho thấy đuôi dài; p50 tăng cùng p99 có thể là vấn đề tải rộng hơn.
4. **Timeout và lỗi có tăng không?** Nếu request chậm nhất timeout và bị loại khỏi latency histogram, p99 của request thành công có thể giảm trong lúc hệ thống xấu đi.
5. **Throughput, concurrency và tài nguyên** có thay đổi cùng thời điểm không?

### Phân biệt bốn dạng đồ thị

| Hiện tượng | Giả thuyết ban đầu | Cần kiểm tra tiếp |
|---|---|---|
| p50 ổn, p99 đọc tăng đột biến | Một số partition/query chậm, disk stall, tombstone scan | Bảng/partition nóng, SSTables per read, tracing, node lệch |
| p50 và p99 đều tăng | Cả hệ thống đang chật tài nguyên hoặc network rộng | Traffic, CPU, GC, compaction, I/O, saturation |
| p99 driver cao, table-local latency thấp | Chậm ở queue, coordinator, retry, network/WAN | Driver metrics, coordinator metrics, request timeout, network |
| p99 read/write giảm nhưng timeout tăng | **Survivorship bias**: request chậm thất bại và không nằm trong mẫu thành công | Tính SLI với cả timeout/error, đếm tổng attempts |

**Không chỉ theo dõi tỷ lệ p99/p50.** Chênh lệch lớn là tín hiệu điều tra, không phải bản thân nó chứng minh hệ thống có lỗi.

## 6. Trung bình của các phân vị là sai

Một lỗi phổ biến khi tổng hợp metrics đa node là:

~~~text
p99_cluster = average(p99_node_1, p99_node_2, p99_node_3)
~~~

Cách này **không đúng về toán học**. Percentile không thể được tổng hợp bằng trung bình số học, kể cả khi lượng request trên các node bằng nhau. Mỗi p99 chỉ nói về phân bố ở node riêng; không chứa đủ thông tin về các vị trí còn lại của phân bố toàn cluster.

### Ví dụ đơn giản

- Node A xử lý 10.000 request với p99 = 20 ms.
- Node B xử lý 100 request với p99 = 2.000 ms.

Trung bình hai p99 là 1.010 ms, nhưng node A chiếm gần như toàn bộ traffic. **p99 thực tế của tập 10.100 request phải tính từ phân bố hợp nhất**, không lấy trung bình 20 và 2.000.

**Cách đúng:** thu thập các histogram có bucket tương thích từ những node/instance cần gộp, **cộng số lượng quan sát theo từng bucket**, rồi tính phân vị từ histogram hợp nhất. Hoặc dùng telemetry có thể tính quantile toàn cục từ distribution phù hợp.

Trong Prometheus, ví dụ kiểu truy vấn **minh họa cho histogram chuẩn đã instrument**:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, operation) (
    rate(app_cassandra_request_duration_seconds_bucket[5m])
  )
)
~~~

Đây **không phải tên metric Cassandra mặc định**. Nó giả định ứng dụng đã xuất histogram `app_cassandra_request_duration_seconds_bucket` với nhãn `le` và `operation`. Tên thực tế tùy collector. Không áp dụng truy vấn này cho Prometheus summary quantiles (dạng `quantile="0.99"`) rồi cộng/trung bình các quantile ấy.

Khi dùng histogram, độ chính xác p99 phụ thuộc vị trí bucket; nếu bucket quá thưa quanh SLA, kết quả là xấp xỉ khá thô. Cần chọn bucket phù hợp ngưỡng độ trễ quan tâm và chú ý cardinality nhãn.

## 7. Cửa sổ đo, SLO và error budget

### 7.1. p99 một phút và p99 một ngày trả lời câu hỏi khác nhau

- **Cửa sổ ngắn** (1–5 phút): giúp phát hiện spike, nhưng dao động lớn nếu traffic ít.
- **Cửa sổ dài** (30 phút–24 giờ): tốt để nhìn xu hướng, song có thể che burst vài phút.
- **SLO window** (ví dụ 30 ngày): đánh giá chất lượng theo cam kết, không thay dashboard điều tra tức thời.

Một p99 của 24 giờ không thể được dựng lại chính xác bằng cách lấy trung bình 24 giá trị p99 theo giờ.

### 7.2. SLO dạng tỷ lệ request tốt

Ví dụ đội backend định nghĩa:

> Trong 30 ngày, ít nhất 99,9% các yêu cầu đọc `getDeviceEvents` phải thành công và hoàn thành không quá 150 ms tại biên ứng dụng đo Cassandra.

Với **100.000 request** trong cửa sổ, ngân sách số request không đạt là:

~~~text
Tổng request = 100.000
SLO good ratio = 99,9%
Error budget = 0,1% × 100.000 = 100 request

Good request:
    thành công VÀ duration <= 150 ms

Bad request:
    lỗi, timeout HOẶC duration > 150 ms
~~~

Cách tính này không để những request timeout biến mất khỏi thống kê. Nếu một bộ đo latency chỉ ghi nhận request thành công, cần **SLI song song** cho error/timeout hoặc sử dụng bộ đếm good/bad bao quát tất cả request.

SLO **không bắt buộc chỉ được biểu diễn bằng p99**. Ngưỡng good-request ratio thường diễn giải dễ và dùng được để tính error budget. p50/p95/p99 vẫn giúp chẩn đoán khi SLO giảm.

### 7.3. Tránh đánh đồng server latency với mục tiêu người dùng

Nếu SLO được đo ở biên HTTP 300 ms nhưng Cassandra server-local p99 là 30 ms, vẫn có thể vi phạm SLO vì driver retry, queue, network, serialization hoặc backend khác. SLO ở **trải nghiệm người dùng** và SLO ở **truy cập Cassandra** nên có tên, phạm vi và owner tách biệt.

## 8. Từ log, metrics đến dashboard Cassandra

### 8.1. Những gì nên quan sát cùng nhau

| Nhóm số đo | Ví dụ | Vì sao cần |
|---|---|---|
| **Read latency** | p50/p95/p99 theo keyspace/table/query và DC | Phát hiện read tail và partition nóng |
| **Write latency** | p50/p95/p99 theo CL và loại ghi | Phát hiện slow replica, commit log, mutation pressure |
| **Throughput** | Read/s, write/s, concurrency | Phân biệt tăng tải với suy giảm hiệu quả |
| **Error** | Unavailable, timeout, overload, retry attempts | Không để request lỗi ra khỏi báo cáo |
| **Tài nguyên** | CPU, GC pause, disk read/write latency, queue | Tìm nghẽn khiến tail tăng |
| **SSTable/compaction** | SSTables per read, pending compactions, tombstone scan | Giải thích read amplification |
| **Replica/topology** | Node UP/DOWN, DC, rack, hints/repair/streaming | Giải thích thời điểm cần chờ replica chậm |
| **Driver/client** | In-flight, connection pool, request duration, retry, speculative executions | Tách độ trễ client khỏi server-local |

Đừng theo dõi tất cả bảng bằng **một con số p99 toàn cluster**. Một API quan trọng chỉ chiếm 5% traffic có thể trở nên rất chậm mà biểu đồ toàn cục ít thay đổi. Nên nhóm theo **operation ổn định**, keyspace/table, datacenter và loại request phù hợp.

### 8.2. Chọn nhãn metrics có cardinality an toàn

Nhãn hợp lý:

- `operation=read_latest_events` hoặc `write_measurement`.
- `keyspace=telemetry`, `table=events_by_device_day`.
- `dc=dc1`, `consistency=LOCAL_QUORUM`.
- `outcome=success|timeout|error`.

Không đưa `partition_key`, `device_id`, `user_id`, raw CQL có giá trị bind, exception message tùy ý hoặc request ID vào nhãn metrics: cardinality tăng không giới hạn, tốn bộ nhớ, lưu trữ và làm hệ thống quan sát quá tải. Khi cần truy vấn chi tiết, dùng logs/traces **được lấy mẫu**, bảo vệ thông tin nhạy cảm và khử dữ liệu cá nhân.

## 9. Công cụ chẩn đoán trực tiếp trong Cassandra

Tên trường/metric và cách hiển thị phụ thuộc phiên bản Cassandra, nên hãy kiểm tra kết quả thật từ cluster thay vì coi ví dụ là output cố định.

### 9.1. Nodetool

~~~bash
# Thống kê bảng: read/write latency, SSTable,
# partition và các chỉ số hỗ trợ theo phiên bản.
nodetool tablestats telemetry.events_by_device_day

# Histogram theo bảng: read/write latency, SSTables per read,
# partition size, cell count... tùy phiên bản.
nodetool tablehistograms telemetry events_by_device_day

# Histogram độ trễ ở tầng coordinator/proxy.
nodetool proxyhistograms

# Các tác vụ compaction và backlog.
nodetool compactionstats

# Thread pools, queue và dropped messages (tùy phiên bản).
nodetool tpstats

# Trạng thái topology và node trong các DC.
nodetool status
~~~

`tablehistograms` đặc biệt hữu ích để kiểm tra khi **chỉ một bảng** có phân phối read latency xấu hoặc nhiều SSTable mỗi lần đọc. `proxyhistograms` quan sát đường request gần coordinator, trong khi metrics table-local có thể khác do phạm vi đo. Không tự cộng các số đo đó.

Cũng có thể lấy metrics qua JMX/Prometheus exporter; **tên metric và đơn vị** (microsecond, millisecond, nanosecond, seconds) cần được xác nhận trong stack cụ thể. Lỗi đổi đơn vị 1.000 lần có thể tạo cảnh báo giả hoặc che cảnh báo thật.

### 9.2. CQL tracing có chọn lọc

Giả sử keyspace/table đã được tạo và ứng dụng thường dùng query có đủ partition key:

~~~cql
TRACING ON;

SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
~~~

Tracing giúp xem một số hoạt động trên coordinator/replica, như request tới replica nào, bước đọc và thời gian tương ứng. Nhưng tracing làm tăng overhead; **không bật liên tục cho toàn bộ lưu lượng production** chỉ để lấy percentile. Percentile phải được thu từ histogram của nhiều request, còn tracing hỗ trợ **điều tra một số request đại diện**.

### 9.3. Phân biệt ảnh chụp và dòng thời gian

Một `nodetool tablehistograms` tại thời điểm T chỉ là quan sát của bộ số liệu theo phạm vi/tính chất công cụ. Để nhận biết spike p99 xảy ra khi nào, cần time-series export và retention phù hợp.

Khi xem dashboard, luôn đặt biểu đồ p99 cạnh traffic rate, timeout, dropped messages, disk latency, compaction và GC cùng mốc thời gian.

## 10. Ví dụ CQL: cùng một API, hai cách truy vấn có độ trễ khác nhau

Giả sử API lấy các sự kiện gần nhất theo thiết bị và ngày. Thiết kế schema:

~~~cql
-- Giả sử keyspace telemetry đã tồn tại.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Truy vấn xác định đầy đủ partition key:

~~~cql
CONSISTENCY LOCAL_QUORUM;

SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Ngược lại, truy vấn lọc theo metric không có partition key:

~~~cql
-- Minh họa truy vấn dễ gây đọc rộng; tránh dùng như API mặc định.
SELECT device_id, event_day, event_time, metric_value
FROM telemetry.events_by_device_day
WHERE metric_value > 80
ALLOW FILTERING;
~~~

`ALLOW FILTERING` không biến truy vấn thành lookup theo partition key. Nếu API thực sự cần query theo metric, hãy thiết kế một bảng phục vụ truy vấn đó hoặc đánh giá index/search theo phiên bản và dữ liệu thực tế.

Tuy nhiên **truy vấn đúng partition key vẫn có thể có p99 xấu** nếu partition quá lớn, nhiều SSTable, nhiều tombstone hay có hot key. Khi thấy một nhóm API chậm, nên kiểm tra **cả query shape lẫn storage amplification**, không chỉ sửa `LIMIT`.

## 11. Ví dụ Java Driver 4.x: đo request duration đúng chỗ

Để đo latency tại ứng dụng Java, dùng đồng hồ đơn điệu `System.nanoTime()` và ghi vào một hệ metrics/histogram có thể tính phân vị. Ví dụ sử dụng **Micrometer** (cần thêm dependency Micrometer phù hợp vào project), với `CqlSession` được quản lý bởi vòng đời ứng dụng.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class EventReadRepository {
    private final CqlSession session;
    private final PreparedStatement select;
    private final Timer successTimer;
    private final Timer failureTimer;

    public EventReadRepository(CqlSession session, MeterRegistry registry) {
        this.session = session;
        this.select = session.prepare(
            "SELECT event_time, metric_value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 50"
        );
        this.successTimer = Timer.builder("app.cassandra.read.duration")
            .tag("query", "events_by_device_day")
            .tag("cl", "LOCAL_QUORUM")
            .tag("outcome", "success")
            .publishPercentileHistogram()
            .register(registry);
        this.failureTimer = Timer.builder("app.cassandra.read.duration")
            .tag("query", "events_by_device_day")
            .tag("cl", "LOCAL_QUORUM")
            .tag("outcome", "error")
            .publishPercentileHistogram()
            .register(registry);
    }

    public List<Row> read(UUID deviceId, LocalDate day) {
        BoundStatement statement = select.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
        long started = System.nanoTime();
        Timer timer = successTimer;
        try {
            return session.execute(statement).all();
        } catch (RuntimeException ex) {
            timer = failureTimer;
            throw ex;
        } finally {
            timer.record(System.nanoTime() - started, TimeUnit.NANOSECONDS);
        }
    }
}
~~~

Đây là ví dụ instrument một đường **đọc đồng bộ**. Timer đo từ trước `execute` đến khi lấy danh sách kết quả tối đa 50 row, có thể gồm các vòng xử lý của driver, network, coordinator và server. Nó **không** đo toàn bộ thời gian API HTTP nếu phần xử lý khác nằm ngoài hàm.

Lưu ý vận hành:

- Dùng `publishPercentileHistogram()` để có dữ liệu phân phối có thể gộp phù hợp với backend quan sát hỗ trợ; cấu hình bucket/SLO theo nhu cầu.
- Tách `outcome=success` và `outcome=error` để không làm mất dấu request thất bại; SLO tổng vẫn phải đếm cả hai nhóm.
- Khi cần phân biệt `timeout`, `unavailable`, `overload`, có thể phân loại exception thành **tập nhãn nhỏ, cố định**.
- **Không gắn `deviceId`, `event_time` hay nội dung CQL bind vào metric tags**.
- Với truy vấn phân trang, phải quyết định đo **mỗi page/driver request** hay **toàn bộ API đã đọc hết trang**; hai metric không tương đương.
- Với phương thức async, không đặt `finally` bao quanh `executeAsync(...)` rồi coi đó là thời gian hoàn tất truy vấn; phải kết thúc timer khi completion stage hoàn thành.

### Cách theo dõi ghi

Với `INSERT`/`UPDATE`, dùng Timer tương tự nhưng tên/nhãn `operation=write_measurement`, `cl=LOCAL_QUORUM`, và giữ riêng **regular write** với **LWT**. Điều này cho phép phát hiện p99 ghi tăng mà không làm nhiễu số đo đọc.

Khi làm benchmark, không ghi từng request ra stdout: logging quá dày có thể tự làm tăng tail latency. Metrics nên dùng bộ ghi phù hợp với sản lượng production và kiểm soát chi phí ghi nhận.

## 12. Quy trình điều tra p99 tăng trong production

Giả sử một service ghi telemetry cho biết **p99 read tăng từ 70 ms lên 900 ms**, trong khi average chỉ nhích nhẹ. Tránh thay đổi compaction strategy hoặc tăng timeout ngay. Hãy điều tra theo thứ tự.

### Bước 1 — Xác minh tín hiệu và phạm vi

Ghi rõ thời điểm bắt đầu, khoảng đo, số request, p50/p95/p99, retry/timeouts và định nghĩa timer. Phân tách theo API, query signature, keyspace/table, DC và CL. Xác nhận đây là **độ trễ client** hay **storage-local**.

### Bước 2 — So với tải và nguyên nhân bên ngoài

Xem QPS/concurrency, mức tăng traffic, deploy Java app, thay đổi network/WAN, tình trạng node UP/DOWN, GC, disk latency, streaming/repair và pending compactions. Nếu mọi API đều tăng p99, xem hạ tầng chung trước.

### Bước 3 — Kiểm tra query shape

Xem query có đủ partition key không, dải clustering có quá rộng không, có `ALLOW FILTERING` hoặc query mới ra mắt không. Nếu chỉ một nhóm partition chậm, xem hot/wide partition và skew của traffic.

### Bước 4 — Quan sát read amplification

Đối chiếu `nodetool tablehistograms`, SSTables per read, tombstone warning/scan và compaction backlog. Khi TTL/DELETE tạo vùng tombstone lớn, một query `LIMIT 20` vẫn có thể quét nhiều dữ liệu.

### Bước 5 — Tách coordinator, replica và driver

Nếu table-local latency thấp nhưng client p99 cao, kiểm tra network, coordinator queues, retries, speculative requests, contact points, connection pooling và read CL. Nếu node cụ thể có disk/GC chậm, tìm lý do slow replica thay vì tăng tài nguyên toàn cluster một cách mù quáng.

### Bước 6 — Thử thay đổi nhỏ, đo trước/sau

Có thể giới hạn clustering range, sửa query/data model, điều chỉnh backpressure của import, xử lý compaction backlog hoặc cô lập tác vụ streaming. Chỉ chỉnh timeout, speculative retry hoặc CL khi hiểu tác động lên correctness, availability và overload.

### Bước 7 — Xác minh không đánh đổi lỗi để có p99 đẹp

So p99 và error/timeout rate ở cùng khoảng thời gian; tính good-request ratio của SLO. Nếu p99 giảm nhưng timeout tăng, không thể tuyên bố đã giải quyết vấn đề. Cần giữ nguyên định nghĩa phép đo và xem biến động trên đủ lượng mẫu.

## 13. Các lỗi thường gặp khi quan sát latency

| Ngộ nhận | Vì sao sai | Cách làm đúng |
|---|---|---|
| “Average dưới 100 ms nghĩa là khách hàng ổn” | Đuôi rất chậm có thể chỉ chiếm 1–2% | Theo p95/p99 và SLO |
| “Lấy trung bình p99 các node sẽ ra p99 cluster” | Quantile không có tính cộng | Gộp histogram bucket đúng cách |
| “p99 tốt hơn sau sự cố” | Request chậm có thể timeout và bị loại khỏi mẫu | Theo cả error/timeout và latency |
| “Node local latency nhỏ nên Cassandra không thể gây chậm” | Coordinator, replica khác, network, queue và retry không nằm trong metric đó | Đo đa lớp |
| “Mọi SELECT nên có cùng p99” | Query shape, partition size và bảng khác nhau | Phân nhóm theo operation/table/CL |
| “p99 tăng thì thêm cache” | Có thể do tombstone, SSTable, WAN, compaction, hot key | Đo nguyên nhân trước khi chỉnh |
| “Bật tracing mọi request để tính p99” | Tracing có overhead và không thay histogram | Trace có chọn lọc, metrics đo liên tục |
| “Đổi từ QUORUM sang ONE để p99 thấp hơn” | Thay đổi consistency/correctness và khả năng đọc kết quả | Chỉ thay nếu yêu cầu nghiệp vụ cho phép |
| “Mỗi device_id một metric label giúp debug” | Cardinality nổ theo số thiết bị | Chỉ tag giá trị hữu hạn; dùng logs/traces chọn lọc |
| “p99 của 10 request rất đáng tin” | Percentile cực cao cần đủ mẫu | Xem sample count và cửa sổ dài hơn |

## 14. Bài tập tự kiểm tra

**Câu 1.** Một bảng có average read latency 100 ms, p50 50 ms và p99 2.550 ms. Có thể kết luận hệ thống ổn vì average chỉ 100 ms không?

**Đáp án:** Không. p99 2.550 ms nghĩa là khoảng 1% đuôi chậm ở mức giây, có thể vi phạm mục tiêu trải nghiệm; cần xem QPS, timeout và nhóm query bị ảnh hưởng.

**Câu 2.** Node A có p99=20 ms ở 10.000 request; node B có p99=2.000 ms ở 100 request. p99 toàn cluster có phải 1.010 ms?

**Đáp án:** Không. Trung bình p99 các node là phép tổng hợp không hợp lệ; phải gộp phân bố/histogram rồi tính quantile.

**Câu 3.** Request `SELECT` trả 20 row nhưng phải quét 5.000 tombstone. Vì sao read p99 cao dù `LIMIT 20`?

**Đáp án:** Cassandra cần bỏ qua nhiều entry bị xóa/hết hạn trước khi tìm đủ row còn sống, dẫn đến read amplification trên replica.

**Câu 4.** Server-local write latency p99=15 ms, nhưng Java request p99=600 ms. Hãy nêu ít nhất ba lớp cần kiểm tra.

**Đáp án:** Driver queue/retry, coordinator queue, WAN/network, replica chậm khác, GC, timeout trước thành công, serialization/logic client. Không lấy hiệu hai p99 làm network p99.

**Câu 5.** Sau khi sửa hệ thống, p99 read từ 900 ms xuống 100 ms nhưng timeout rate tăng từ 0,1% lên 5%. Đây có phải cải thiện rõ ràng?

**Đáp án:** Không. Nếu percentile chỉ tính request thành công, những request chậm đã thành timeout và biến khỏi histogram. SLO good-request ratio có thể tệ hơn nhiều.

**Câu 6.** Trong một cửa sổ có 100.000 request, SLO yêu cầu 99,9% thành công dưới 150 ms. Tối đa bao nhiêu request có thể vi phạm để vẫn đạt SLO?

**Đáp án:** Tối đa 100 request (0,1%); tính lỗi, timeout và request vượt ngưỡng vào số vi phạm.

**Câu 7.** Vì sao không gắn partition key làm nhãn histogram?

**Đáp án:** Số lượng partition có thể rất lớn; cardinality tăng không giới hạn khiến telemetry đắt và có thể quá tải. Chỉ dùng nhãn ít giá trị, kết hợp logs/traces mẫu để điều tra partition đặc thù.

## 15. Tổng kết

Trong Apache Cassandra, **read/write latency là phân bố**, không phải một con số average. Độ trễ đuôi có thể đến từ một số partition, một số replica, đường network, coordinator, Java Driver hoặc những công việc nền như compaction và repair.

Cách quan sát hiệu quả là:

1. **Đo p50/p95/p99** và throughput của đọc/ghi riêng biệt; khi đủ số mẫu, theo dõi cả p99.9.
2. **Phân biệt tầng đo**: end-to-end app, driver/coordinator và table-local trên replica.
3. **Không lấy trung bình các percentile** từ nhiều node; gộp histogram hoặc dùng dữ liệu phân phối có thể tổng hợp.
4. **Đếm cả timeout và error**; một p99 của request thành công không nói hết chất lượng dịch vụ.
5. **Gắn kết percentile với nguyên nhân Cassandra**: partition key, query shape, CL, SSTable/tombstone, replica, I/O và WAN.
6. **Dùng SLO và cửa sổ đủ mẫu** để phân biệt bất thường nhất thời với suy giảm chất lượng ảnh hưởng người dùng.

Khi average vẫn đẹp mà p99 tăng, câu hỏi đúng không phải “tại sao trung bình chưa vượt ngưỡng?”, mà là **“nhóm request chậm nhất đang đi qua đường nào, bị chặn ở đâu, và tỷ lệ người dùng bị ảnh hưởng là bao nhiêu?”**. Trả lời được ba câu đó mới giúp tối ưu Cassandra có cơ sở thay vì đổi cấu hình theo cảm giác.
