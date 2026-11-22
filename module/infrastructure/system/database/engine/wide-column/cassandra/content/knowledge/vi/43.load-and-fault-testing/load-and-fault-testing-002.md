# Dữ liệu đại diện về kích thước, phân vùng, TTL và tỷ lệ cập nhật

> **Chương:** Đo tải và lỗi phân tán  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — học Apache Cassandra phân tán và mô hình wide-column, partition key, thiết kế bảng theo truy vấn, consistency đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java.

Giả sử một đội đo hiệu năng Cassandra bằng cách ghi 1 triệu hàng, mỗi hàng chứa chuỗi `"hello"`, partition key được chọn ngẫu nhiên đều, không có TTL hay UPDATE. Test cho p99 rất đẹp. Nhưng hệ thống thật lưu sự kiện thiết bị theo ngày, 1% thiết bị tạo gần một nửa lưu lượng, payload thay đổi từ vài chục byte đến hàng chục KiB, một phần dữ liệu hết hạn sau 7 ngày, một số hàng bị cập nhật lại nhiều lần. Khi một replica lỗi, read latency và tombstone scan của dữ liệu lâu ngày tăng mạnh. **Bộ dữ liệu thử nghiệm đã bỏ lỡ đúng các đặc điểm làm hệ thống thật chậm.**

Bài này hướng dẫn thiết kế **tập dữ liệu đại diện (representative dataset)** cho load testing và fault testing trên Apache Cassandra. Mục tiêu không phải sao chép dữ liệu người dùng, cũng không phải tạo con số QPS tối đa bằng mọi giá. Mục tiêu là có một mô hình có thể lặp lại, đo được và giải thích được:

- **Kích thước:** phân phối bytes của row, payload, collection, partition và kích thước trên đĩa sau compression/replication.
- **Phân vùng:** số partition, số rows/partition, khóa nóng/lạnh, token locality và độ lệch giữa các replicas.
- **TTL/tuổi:** tỷ lệ dữ liệu còn sống, sắp hết hạn, đã hết hạn; tombstones và trạng thái compaction theo thời gian.
- **Tỷ lệ cập nhật:** bao nhiêu INSERT tạo mới, UPDATE chạm hàng cũ, DELETE, LWT, read theo PK/range; cùng temporal locality và burst.
- **Tải và lỗi:** kiểm thử trên **cùng trạng thái dữ liệu** trước, trong và sau khi gây lỗi node/network/disk; không thay đổi workload tùy ý rồi kết luận do fault.

> **Phạm vi:** Cassandra 4.x–5.x, CQL và Java Driver 4.x, `cassandra-stress` user mode để minh họa; cấu hình công cụ, compaction và metric phải đối chiếu bản server thật. Tất cả số trong bảng “profile lab” đều là **dữ liệu giả định để thiết kế thử nghiệm**, không phải số liệu production được thu thập hoặc ngưỡng SLA chung.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Lập **data/workload profile** từ phân phối thực tế, thay vì chỉ đặt tổng số rows và QPS.
2. Tính quy mô sơ bộ theo logical bytes, replication factor, compression và chi phí storage amplification mà không nhầm số bytes trên wire với bytes SSTable.
3. Sinh partition keys theo uniform, skew/hotset, bucket theo thời gian và đảm bảo UPDATE thật sự chạm keys đã tồn tại.
4. Tạo payload với nhiều kích cỡ, nhiều mức entropy, nullable/collections phù hợp để đo compression, codec, GC và network.
5. Dựng TTL cohorts và tombstone pressure **có tuổi thọ thật**, hiểu vì sao backdate `event_time` không khiến TTL tự hết hạn.
6. Điều phối tỷ lệ INSERT/UPDATE/DELETE/READ có kiểm soát; phân biệt update cột với whole-row upsert và LWT.
7. Viết generator Java có seed tái lập, prepared statements, backpressure/concurrency limit, rate control và manifest.
8. Dùng `cassandra-stress user` hoặc workload runner tùy biến đúng mục đích, biết giới hạn của profile tổng quát.
9. Thiết kế các pha prefill, warm-up, steady-state, fault, recovery/soak và so sánh bằng cùng baseline.
10. Đọc các chỉ số `EstimatedPartitionSizeHistogram`, `TombstoneScannedHistogram`, SSTables/read, compaction và p95/p99; từ chối một run có dữ liệu sai profile.

## 2. “Đại diện” nghĩa là gì?

### 2.1. Khối lượng lớn chưa chắc giống workload thật

| Bộ dữ liệu | Điều test được | Điều dễ bỏ sót |
|---|---|---|
| 10 triệu keys đều, mỗi key đúng 1 row | Throughput hashing/network với dữ liệu “skinny” | Wide partitions, hot keys, clustering range |
| 1 key chứa 10 triệu rows | Extreme wide-partition behavior | Độ cân bằng token/replica, nhiều partition bình thường |
| 1 KiB payload lặp lại toàn ký tự `A` | Một trường hợp dữ liệu **rất dễ nén** | Disk/network ratio với JSON/blob entropy cao |
| Mọi INSERT có TTL 60 s | Đường TTL ngắn | Hỗn hợp TTL dài/không TTL và SSTable life-cycle thật |
| Chỉ INSERT mới, không UPDATE/DELETE | Write ingestion throughput | Write amplification, tombstones, read-before-write của list |
| 99% đọc cùng một key | Hot-key behavior | Hệ thống phần lớn cold keys và fan-out |
| 5 phút test sau khi truncate | Startup/short burst | LSM ổn định, compaction/repair pressure, aged tombstones |

Kết quả phải được ghi nhãn: **microbenchmark**, **capacity baseline**, **workload realism**, **failure-recovery** hay **soak**. Không dùng microbenchmark payload 8 B để dự đoán p99 của API thật có 2 KiB JSON/row và hot partitions.

### 2.2. Tập dữ liệu đại diện có ít nhất bốn phân phối

~~~mermaid
flowchart TD
    A["Tín hiệu workload thực / giả định có ghi nhãn"] --> B["Partition distribution"]
    A --> C["Row & payload bytes / entropy"]
    A --> D["TTL / age & tombstone cohorts"]
    A --> E["Mutation & query mix"]
    B --> F["Generator có seed + manifest"]
    C --> F
    D --> F
    E --> F
    F --> G["Prefill & aging"]
    G --> H["Đo snapshot baseline"]
    H --> I["Load + fault injection"]
    I --> J["Validate fidelity, p95/p99, lỗi, recovery"]
~~~

**Distribution phải có correlation**, không chỉ bốn histogram độc lập: ví dụ các thiết bị nóng có nhiều sự kiện hơn, payload to hơn hoặc TTL khác; read thường hướng về dữ liệu mới, UPDATE hướng về những hàng đã tồn tại gần đây. Sinh tất cả biến độc lập theo uniform có thể tạo tổ hợp hiếm gặp mà thực tế không có, hoặc bỏ lỡ các tổ hợp xấu nhất.

### 2.3. Dữ liệu thực không được sao chép trực tiếp

Để xây profile từ production telemetry, **chỉ dùng thống kê tổng hợp đã được phê duyệt**:

- Histogram bytes của payload (không giữ nội dung thô).
- Percentile rows/partition và maximum (ẩn danh key).
- Top-k hot-key **theo hash không đảo được**, không log tenant/device IDs thật.
- TTL policy theo loại bản ghi, tỷ lệ expired/deleted.
- Số requests theo query type/CL/consistency, tỷ lệ update/delete.
- Arrival pattern theo giờ/ngày; peak/burst và thời gian hồi phục.

Không mang raw PII, secrets, access tokens, IP cá nhân hoặc dữ liệu thanh toán lên cluster lab. Nếu có yêu cầu fidelity cao, hãy **tổng hợp thống kê riêng tư** hoặc dùng synthetic data theo phân phối đã quan sát, kiểm soát quyền truy cập và retention trong lab.

## 3. Viết “hồ sơ dữ liệu” trước khi chạy thử

Một hồ sơ có thể diễn đạt như sau; **các số dưới đây chỉ là ví dụ giả định**:

| Nhóm biến | Profile minh họa | Vì sao đo |
|---|---|---|
| Quy mô keys | 200.000 devices; mỗi key gắn một ngày | Xác định số partitions logic |
| Rows/partition | p50=12, p95=250, p99=1.000, max=5.000 | Bắt long tail và wide partitions |
| Payload | 55% 128–512 B; 35% 1–4 KiB; 10% 8–32 KiB | Network, compression, GC |
| Payload entropy | 40% JSON-like, 50% high-entropy, 10% low-entropy | Tránh payload toàn ký tự `A` |
| TTL trên event writes | 20% no TTL; 60% 7 ngày; 20% 30 ngày | Mixed expiration và tombstones |
| Tỷ lệ operations tổng | SELECT 55%, INSERT 25%, UPDATE 15%, DELETE 5% | Áp lực đọc/ghi theo business |
| Tính nóng/lạnh | Top 1% partition keys nhận 40% *requests* | Replica skew, cache |
| Read recency | 80% đọc 48 giờ gần nhất | Cache và range/read locality |
| Update recency | 85% UPDATE chạm event tạo trong 24h gần nhất | Hàng có thật, không upsert ẩn |
| Fault phase | Mất 1 replica trong RF3 local DC trong lab | Khả năng giữ CL và recovery |

**Không trộn bừa một profile giả định thành kết luận môi trường thật**. Cần ghi nguồn gốc ước lượng, cỡ mẫu, khoảng thu thập, giờ cao điểm, confidence và các dimensions không đo được.

### 3.1. Phân biệt tỷ lệ theo request và theo row/byte

Một `SELECT` có thể đọc 1 hàng hoặc 1.000 hàng. Một INSERT 8 KiB có thể tốn hơn nhiều lần INSERT 128 B. Do đó, “55% SELECT” chỉ là tỷ lệ **requests**, không có nghĩa 55% rows hay 55% bytes được xử lý.

Ghi đồng thời:

- **ops/s** theo loại CQL và số requests bắt đầu/thành công/thất bại.
- **rows/op** và **bytes/op** (ước lượng application) theo loại.
- **pages/op** trên các query paginated.
- **hot-key request share** và hot-key byte share riêng.
- **retry/speculative executions** riêng, vì một business request có thể tạo nhiều executions ở driver.

### 3.2. Phân phối chiều rộng partition

Với một partition `(device_id, event_day)`, số rows phụ thuộc cả lưu lượng của thiết bị **và** thời gian bucket. Nên ghi histogram bằng **rows/partition**, **live bytes/partition** và **tombstones/partition**, không chỉ tổng số thiết bị.

Nếu một thiết bị có 500.000 events/ngày, bucket theo ngày có thể quá rộng; cân nhắc bucket giờ hoặc một thành phần shard trong partition key sau khi đã đo và xét query. **Không thêm shard ngẫu nhiên chỉ để cân bằng token** mà quên rằng read mới cần fan-out qua các shards.

### 3.3. Phân phối “nóng” có hai nghĩa

1. **Hot by size:** một số partitions lưu nhiều rows/bytes, làm compaction/read scan nặng.
2. **Hot by requests:** một số partitions bị hỏi liên tục, dồn tải lên replica set.

Hai tập có thể trùng hoặc khác nhau. Một partition nhỏ chỉ có một row nhưng được đọc 100.000 lần/phút vẫn nóng. Ngược lại, một partition 50 MiB hiếm đọc cũng có thể gây p99 xấu khi đọc hết.

## 4. Schema lab theo truy vấn: events và state

### 4.1. Topology giả định

Phần CQL giả định một **cluster thử nghiệm riêng** có ba nodes trong datacenter thực tên `dc1`, RF=3. Trước khi tạo schema:

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

Nếu lab chỉ một node, đổi RF=1 và CL tương ứng cho bài codec/size cơ bản. **Một node không thể xác minh khả năng chịu fault của RF3/LOCAL_QUORUM**; test node-down cần topology multi-node thật hoặc môi trường mô phỏng mạng đã kiểm chứng.

~~~sql
CREATE KEYSPACE IF NOT EXISTS load_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

### 4.2. Bảng sự kiện theo thiết bị và ngày

~~~sql
CREATE TABLE IF NOT EXISTS load_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload blob,
    event_type text,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Giải thích khóa:**

- Partition key là `(device_id, event_day)`: giới hạn vùng dữ liệu một thiết bị trong một ngày.
- Clustering `event_time DESC` phù hợp query “lấy sự kiện mới trước”; `event_id` làm tie-breaker.
- Có thể UPDATE một sự kiện khi biết **đầy đủ primary key**; không cần index trên status để đọc theo thiết bị/ngày.
- `payload blob` được dùng để sinh kích thước/entropy ổn định, tránh chi phí JSON encoder không kiểm soát. Trong ứng dụng thật, có thể là text/UDT/collections.
- Không chọn compaction strategy tùy tiện trong DDL. Trên Cassandra 5.x, UCS được khuyến nghị cho nhiều workload; TWCS phù hợp một số time-series/TTL patterns nhưng cần kiểm chứng tình huống out-of-order/mixed TTL. Dùng strategy được chọn riêng cho bài thử.

Đọc theo pattern đã thiết kế:

~~~sql
SELECT event_time, event_id, event_type, status
FROM load_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 100;
~~~

### 4.3. Bảng state để UPDATE đúng một key

~~~sql
CREATE TABLE IF NOT EXISTS load_lab.device_state_by_id (
    device_id uuid PRIMARY KEY,
    current_state text,
    revision bigint,
    updated_at timestamp,
    attributes map<text, text>
);
~~~

Query phục vụ UPDATE theo PK:

~~~sql
UPDATE load_lab.device_state_by_id
SET current_state = 'ACTIVE', revision = 2,
    updated_at = '2026-11-21T12:00:00Z'
WHERE device_id = 11111111-1111-4111-8111-111111111111;
~~~

Đây là **upsert** bình thường: nếu không prefill state, UPDATE sẽ tạo một hàng mới. Vì vậy generator phải giữ **catalog keys đã tồn tại** và test kiểm tra tỷ lệ INSERT thật/UPDATE thật, không chỉ đếm “request có từ UPDATE”.

Nếu nghiệp vụ yêu cầu optimistic concurrency, một workload riêng dùng `IF revision = ?` sẽ phát sinh LWT/Paxos; **không trộn ngầm** vào cùng tỷ lệ UPDATE thường vì latency và concurrency semantics khác.

### 4.4. Row shape và columns phải sát thực tế

Trong schema thật, có thể có:

- Cột thường NULL/UNSET hoặc một số fields tùy biến.
- Collection nhỏ/UDT nếu nghiệp vụ dùng, không chỉ một blob.
- Nhiều event types với payload khác nhau và tỷ lệ trường null khác nhau.
- TTL ở từng cột/row, deletes/range tombstones và schema history.

Để giữ ví dụ dễ thực hiện, bài dùng một blob + hai text fields. **Không khẳng định schema đơn giản này đại diện cho mọi application Cassandra**: khi tạo profile thật, cần bổ sung mapping/codec phức tạp nếu chúng góp đáng kể vào CPU, network hoặc GC.

## 5. Kích thước: từ payload đến partition và disk

### 5.1. Có ít nhất bốn đơn vị kích thước

| Đơn vị | Thành phần | Dùng để trả lời |
|---|---|---|
| **Payload application** | Bytes của nội dung blob/text/JSON | Client marshal/network payload |
| **Serialized CQL row** | Cột, PK/CK, type encoding, protocol framing | Network/request/response và codec cost |
| **Logical partition** | Nhiều clustering rows + static/metadata/tombstones | Wide partition, scan/paging |
| **Physical SSTable/replicas** | Compression, index/Bloom, fragments, compaction, RF | Disk capacity và IO thực |

`rows × average payload` là **ước lượng nền**, không phải số byte SSTable thật. Cassandra có compression chunks, metadata, partition indexes, SSTable components, tombstones, nhiều SSTables trước compaction, snapshots/hints/commitlog và replica copies.

### 5.2. Ví dụ 1 triệu rows x 1 KiB

~~~text
1,000,000 rows × 1,024 B payload = 1,024,000,000 B
≈ 0.954 GiB dữ liệu payload logic (chưa có row/partition overhead).

RF = 3:
≈ 2.861 GiB là tổng payload copies lý thuyết trên các replicas
  TRƯỚC khi tính compression, indexes, compaction, tombstones và overhead.
~~~

**Không** lấy 2.861 GiB làm disk provision cuối cùng. Nếu nội dung nén rất tốt, live SSTable bytes có thể nhỏ hơn; nhưng trong lúc flush/compaction/snapshot, disk peak có thể cao hơn nhiều lần live size. Cần đo hệ số thực trên thiết bị/mạng/cấu hình được kiểm thử rồi dự trù headroom, không sao chép một tỷ lệ “×3 là đủ”.

### 5.3. Percentiles quan trọng hơn mean

Ví dụ hai profile có cùng average row size 1 KiB:

| Profile | Phân phối kích cỡ | Điểm khác |
|---|---|---|
| A | 100% 1 KiB | Không có đuôi lớn |
| B | 90% 128 B, 9% vài KiB, 1% vài chục KiB | Đuôi p99 ảnh hưởng GC, serialization, network, paging |

Đừng chỉ đặt `payload = new byte[1024]`. Ít nhất đo/báo:

~~~text
row_payload_bytes: p50, p90, p95, p99, max
partition_rows:    p50, p95, p99, max
partition_bytes:   p50, p95, p99, max
query_result_rows: p50, p95, p99, max
payload_entropy:   low / medium / high hoặc một metric được định nghĩa
~~~

Nếu phân phối đã đo chỉ có bucket [0–1KiB, 1–4KiB, 4–32KiB], generator phải chọn **phân phối bên trong từng bucket** và ghi rõ giả định. Không tự bịa “p99 chính xác” khi dữ liệu gốc không cho phép.

### 5.4. Entropy và compression

Cassandra thường nén SSTables theo cấu hình table. Hai payload có cùng kích thước trên wire nhưng khác khả năng nén:

~~~text
low entropy:
  AAAAAAAAAAAAA... (dễ nén)

medium entropy:
  {"type":"sensor","temperature":...,"tags":[...]} 
  (các key JSON lặp, value thay đổi)

high entropy:
  byte[] sinh ngẫu nhiên / binary đã nén / ciphertext
  (khó nén thêm)
~~~

Không dùng **100% zeros/`A`** để so tốc độ với production JSON/ảnh đã nén. Ngược lại, 100% cryptographic-random bytes cũng có thể đánh giá thấp lợi ích compression của dữ liệu thật. Chọn tỷ lệ entropy từ telemetry/ước lượng được ghi nhãn, rồi **đo lại SSTableCompressionRatio** và disk footprint. Không dùng entropy classes để giả định một hệ số nén cố định.

### 5.5. Partition size phụ thuộc rows × cột, không chỉ payload

Theo tài liệu Apache Cassandra, có thể ước lượng số cell/partition bằng:

\[
N_v = N_r (N_c - N_{pk} - N_s) + N_s,
\]

với `N_r` = clustering rows, `N_c` = tổng số columns, `N_{pk}` = các columns thuộc primary key, `N_s` = static columns. Đây là **ước lượng sơ bộ** cho data model; collection non-frozen và tombstones làm cấu trúc cell phức tạp hơn.

Một partition với 3.000 rows × 1 KiB payload không thể đánh đồng partition 3.000 rows × 16 KiB payload. Nếu data model đặt toàn bộ sự kiện theo một `device_id` mà không có time bucket, partition có thể tiếp tục tăng mãi theo retention/growth.

**Ngưỡng partition “lớn” không phải một hằng số thần kỳ.** Tài liệu Cassandra truyền thống nhắc guideline khoảng **dưới 100 MB và dưới 100.000 cells/partition** khi thiết kế; đây là định hướng đánh giá, không phải SLA phù hợp mọi phiên bản/hardware/workload. Đo p95/p99/max và thời gian đọc thực; giữ riêng các ca stress “intentionally oversized” với tỷ lệ rất nhỏ để xác định failure boundary.

## 6. Phân phối partition: đều, lệch và hot keys

### 6.1. Có bao nhiêu partition đang sống?

Với primary key `((device_id, event_day), event_time, event_id)`, số partition thực không phải lúc nào cũng bằng `số devices × số ngày`. Thiết bị không phát sự kiện ngày nào thì **không có partition ngày đó**; thiết bị hoạt động nhiều ngày có nhiều partitions, và TTL có thể làm một số rows hết hạn.

Định nghĩa riêng:

~~~text
device_population             = tổng số thiết bị trong mô hình
active_device_days            = số cặp (device_id, event_day) có sự kiện
live_partitions_at_T          = số partitions còn dữ liệu live tại thời điểm T
rows_per_active_partition     = phân phối rows trong từng device-day
request_weight_per_partition  = xác suất một query/UPDATE truy cập partition đó
~~~

**Không lấy `200.000 devices × 30 days` rồi khẳng định có đúng 6 triệu partitions** nếu chỉ một phần thiết bị hoạt động hàng ngày hoặc nhiều rows đã TTL-expire. Trong manifest, ghi số partitions **đã tạo thật** và có phương pháp kiểm chứng.

### 6.2. Uniform token distribution khác uniform access

Một UUID/hash partition key có thể phân tán token tương đối đều qua Murmur3 và vnodes, nhưng **không phân tán đều lượng request** nếu cùng key được hỏi liên tục.

~~~mermaid
flowchart TD
    A["200k devices, UUIDs phân phối token"] --> B["Replicas/token ranges"]
    C["Top 1% device IDs nhận 40% requests"] --> D["Chỉ một số replica sets phục vụ hot keys"]
    B --> D
    D --> E["CPU/queues/read latency skew"]
    E --> F["Timeout & overload khi một replica lỗi"]
~~~

Một profile uniform chỉ đo khả năng trải tải trên nhiều token, không đo skew. Cần thêm profile **realistic skew** và một profile **worst-case hotset** để xác định giới hạn tải khi các requests dồn vào ít keys.

### 6.3. Sampler hot/cold đơn giản

Ví dụ cấu hình để **top 1% devices nhận 40% request visits**, còn 99% nhận 60%:

~~~java
import java.util.SplittableRandom;

static int chooseDeviceIndex(
        SplittableRandom rng, int devices, int hotDevices) {
    if (devices <= 1 || hotDevices <= 0 || hotDevices >= devices) {
        throw new IllegalArgumentException("Invalid hotset");
    }
    if (rng.nextDouble() < 0.40) {
        return rng.nextInt(hotDevices);
    }
    return hotDevices + rng.nextInt(devices - hotDevices);
}
~~~

Chọn `devices=200_000` và `hotDevices=2_000` để tạo **đúng cấu trúc hotset trên device ID**. Nếu một device có nhiều event_day partitions, top 1% *devices* chưa chắc là top 1% *partitions*: phải đo lại request share ở mức partition key thực tế. Có thể dùng Zipf/Zipf-like distribution hoặc weighted alias sampler để có long tail liên tục thay vì chỉ hai nhóm hot/cold.

### 6.4. Nóng theo thời gian và khi fault xảy ra

Không giữ một tập hot keys vĩnh viễn nếu sản phẩm thật có trào lưu/ca sử dụng theo giờ. Có thể chia run:

- **Hotset cố định:** mô phỏng account/tenant nổi bật liên tục.
- **Hotset xoay vòng mỗi giờ:** mô phỏng ca làm việc/campaign/topic trending.
- **Hotset chuyển sau node failure:** các clients failover/coordinator selection có thể làm một replica khác nhận tải bất ngờ.
- **Bursty hot keys:** 40% requests nằm trong vài phút; average QPS giữ nguyên nhưng peak lớn hơn nhiều.

Khi chạy fault test, phải giữ **cùng quá trình sinh hotset** ở baseline và lỗi, hoặc công khai một thay đổi có chủ đích; nếu không, không biết p99 thay đổi do outage hay do hotset chuyển.

### 6.5. Validate skew thay vì tin vào cấu hình

Sau khi sinh dữ liệu và requests, xuất **chỉ số tổng hợp**:

~~~text
distinct partition keys
requests per hashed partition key: p50/p95/p99/max
top 1% keys share of read/write requests
top 1% keys share of bytes transferred
rows per partition: p50/p95/p99/max
token range / node coordinator requests share
~~~

Nếu muốn xem hot partitions trên node, có thể dùng `nodetool toppartitions` ở bản hỗ trợ; đây là sampler, **không** phải danh sách đầy đủ 100% workload. Không xuất raw tenant/device identifiers sang Prometheus label hoặc public logs.

## 7. TTL, tuổi dữ liệu và tombstones

### 7.1. TTL được tính từ thời điểm ghi, không phải event_time

Trong Cassandra, `INSERT ... USING TTL 604800` khiến các cells được ghi có TTL **604.800 giây = 7 ngày** từ **thời điểm Cassandra xử lý mutation**, không tự căn theo `event_time` là 7 ngày trước.

~~~sql
INSERT INTO load_lab.events_by_device_day
    (device_id, event_day, event_time, event_id,
     payload, event_type, status)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    0x0001AABB,
    'telemetry',
    'NEW'
) USING TTL 604800;
~~~

**Quan trọng:** nếu hôm nay load dữ liệu có `event_time` của 30 ngày trước nhưng ghi `USING TTL 604800`, nó vẫn có khoảng **7 ngày TTL tính từ lúc ghi**, không phải “đã hết hạn từ 23 ngày trước”. Vì vậy **backdating timestamp sự kiện không tạo một SSTable đã có lịch sử TTL thật**.

### 7.2. Kiểm tra TTL còn lại

~~~sql
SELECT event_time, event_id,
       TTL(payload), TTL(status)
FROM load_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

`TTL(column)` trả số giây còn lại hoặc null khi cột không có TTL (hoặc cột không còn live); nó **không trả** “tuổi dữ liệu từ event_time”. Nếu TTL đang giảm trong khi `event_time` giữ nguyên, đó là bình thường. Với blob/text cùng INSERT có `USING TTL`, chúng có thể bắt đầu cùng TTL; update riêng `status` về sau có thể làm TTL của status khác payload.

### 7.3. Xây TTL cohorts và tuổi tombstone

| Cohort | Mục tiêu trạng thái | Cách tạo an toàn trong lab |
|---|---|---|
| Không TTL | Có live cells tồn tại dài hạn | INSERT không dùng TTL |
| TTL dài, còn mới | 7/30 ngày retention theo profile | INSERT với TTL tương ứng |
| Sắp hết hạn | Tạo sớm hơn và chờ qua thời gian đủ; hoặc short TTL lab | **Không** chỉ sửa event_time |
| Vừa hết hạn | Đợi short TTL thật hết, xác minh cột không còn live | Có tombstone/logical expiration |
| Tombstone đã có tuổi | Đợi/soak qua các chu kỳ flush/compaction; dùng lab cô lập | Không ép flush/snapshot rồi gọi là aged |
| Sau reclamation | Quan sát sau điều kiện GC grace/compaction/repair phù hợp | Không tự giả định disk free ngay khi TTL=0 |

Một bài test dài hạn có thể dùng **7 ngày thật** với snapshot/preloaded SSTables được xây qua thời gian; một lab ngắn có thể dùng TTL **90 s / 300 s / 900 s** để quan sát các pha, nhưng **đó chỉ là scale model**. Nó không tự tái hiện fragmentation và repair history của 7–30 ngày.

### 7.4. Đường đời của cell có TTL

~~~mermaid
flowchart LR
    A["INSERT cell có TTL"] --> B["Cell còn sống"]
    B --> C["TTL expires"]
    C --> D["Tombstone / logically deleted"]
    D --> E["Grace + điều kiện an toàn"]
    E --> F["Compaction có thể purge"]
    F --> G["Không còn lưu cell cũ"]
~~~

Tombstone cần thời gian và điều kiện để không làm dữ liệu cũ xuất hiện trở lại khi replica từng offline quay về. Hết `gc_grace_seconds` **không có nghĩa ngay lập tức xóa byte trên disk**; compaction chỉ purge khi thỏa điều kiện an toàn, và trạng thái repaired/unrepaired, overlapping SSTables có thể ảnh hưởng.

**Không rút `gc_grace_seconds` một cách tùy tiện chỉ để benchmark dọn tombstone nhanh**, vì có thể phá recovery safety nếu repair/replica availability không bảo đảm. Mọi thay đổi phải thuộc bài kiểm thử policy có đánh giá rủi ro, không phải mẹo tạo biểu đồ đẹp.

### 7.5. TTL hỗn hợp và compaction

Trong profile ví dụ, 20% event không TTL, 60% TTL 7 ngày, 20% TTL 30 ngày. Nếu cùng một bảng/SSTable chứa cells mới/cũ, TTL khác nhau và update quá hạn, một số SSTables **không thể được drop nguyên file** khi chỉ một phần dữ liệu hết hạn.

Đây là lý do:

- **TWCS** thường hữu ích cho time-series TTL, nhưng có caveat khi late/out-of-order writes trộn nhiều timestamp/tuổi vào cùng SSTable.
- **UCS** ở Cassandra 5.x được khuyến nghị rộng cho nhiều workload, nhưng vẫn cần đo trên data model cụ thể.
- Không cấu hình một compaction strategy “tốt nhất” cho mọi case; lựa chọn phải đi cùng tỷ lệ update, TTL mix và read amplification.

Khi đánh giá TWCS, tránh làm `USING TIMESTAMP` đặt timestamp lịch sử tùy tiện để giả lập thời gian: nó có thể gây nhiều vấn đề hơn là một workload “aged” đúng nghĩa, đặc biệt với out-of-order data.

### 7.6. TTL 0, UPDATE và idempotency

Một UPDATE có TTL mới áp **theo mutation/cells được ghi**, không nhất thiết giữ TTL cũ của các cột đã được ghi lại. Thử lại `INSERT ... USING TTL 604800` sau timeout cũng có thể **gia hạn** deadline lưu trữ so với lần đầu.

Một số quy tắc kiểm thử cần ghi:

- `USING TTL 0` nghĩa là **không TTL / remove TTL** theo CQL semantics, **không phải xóa ngay**.
- Nếu muốn expiry date cố định, phải lưu deadline nghiệp vụ và tính TTL **còn lại** ở mỗi mutation; tuyệt đối tránh biến remaining ≤ 0 thành TTL 0.
- CQL `UNSET` cho một cột bỏ qua mutation; `NULL` xóa cột và có thể tạo tombstone. Phân biệt khi generator tạo partial updates.
- Không dùng các writes có TTL quá ngắn trong prefill rồi chờ hàng biến mất trước khi bắt đầu đo update hit ratio.

### 7.7. Đo tombstones trong đúng giai đoạn

Theo dõi `TombstoneScannedHistogram`, `TombstoneWarnings`, `TombstoneFailures`, compaction backlog, SSTables/read và disk. Không suy “đã có 10.000 expired cells nên mỗi query scan 10.000 tombstones”: cần xét partition/range truy vấn, coverage, compaction và SSTable layout.

Nếu một bài benchmark bắt đầu sau khi **truncate và prefill mới**, nó đang đo một bảng còn “trẻ”; không thể dùng để chứng minh p99 sau tháng đầu có nhiều TTL/deletes.

## 8. INSERT, UPDATE, DELETE và tỉ lệ mutation thực

### 8.1. Cùng số CQL writes, chi phí khác nhau

| Operation | Hành vi | Cần tạo đúng gì trong dataset |
|---|---|---|
| INSERT PK mới | Hàng/cell mới, mở rộng dataset | Identity mới, tỷ lệ inserts thật |
| INSERT cùng PK | Cassandra upsert cells đã có | Lịch sử update/timestamp, không tăng row count nhất thiết |
| UPDATE một cột | Thêm phiên bản cell mới vào LSM | Chọn PK **đã tồn tại**, tránh toàn bộ writes trở thành inserts |
| UPDATE nhiều cột | Thêm mutations của nhiều cells | Column mix, null/unset, TTL reset |
| DELETE một cột/row/range | Tombstones | Tỷ lệ deletes và độ tuổi tombstone |
| LWT UPDATE IF ... | Paxos CAS, có thể false | Conflict rate, serial CL, extra network round trips |
| Counter increment/list append | Non-idempotent writes, semantics riêng | Không retry mù, không gộp vào “UPDATE thường” |

**Cassandra không cập nhật tại chỗ SSTable đã ghi**. UPDATE thêm mutation mới vào write path; compaction về sau hợp nhất versions/tombstones. Nếu test chỉ INSERT rows mới, sẽ bỏ qua công việc read/compaction của workload nhiều updates.

### 8.2. Tỷ lệ update phải dùng khóa có thật

Giả sử 15% của toàn workload là UPDATE:

~~~text
100.000 operations:
  SELECT 55.000
  INSERT 25.000
  UPDATE 15.000
  DELETE  5.000
~~~

Nếu generator chọn UUID ngẫu nhiên toàn cục cho mọi UPDATE, gần như tất cả UUID không tồn tại → **Cassandra vẫn upsert** và bài kiểm thử không có “update hit” như mong muốn.

Tạo/catalog các keys đã prefill, chọn update targets từ danh sách đó, đồng thời kiểm tra thống kê:

~~~text
intended UPDATE request share          = 15%
verified update-target-exists share    ≈ 100% trong profile này
actual row count delta due to UPDATE   ≈ 0 nếu không đổi PK
cells touched/update                   = 1 hoặc vài theo profile
status updates vs payload overwrites   = tỷ lệ riêng
~~~

Chú ý row có thể **hết hạn vì TTL**, nên key trong catalog từ hôm qua chưa chắc còn live hôm nay. Update-target hit ratio phải kiểm tra theo state có tuổi đúng, không chỉ theo danh sách đã từng được insert.

### 8.3. UPDATE hot rows và conflict semantics

Có thể cấu hình:

- 80% updates chạm hàng được tạo gần đây, 20% hàng cũ.
- 70% updates chỉ thay `status`, 30% thay `payload`.
- 10% updates tập trung vào hot devices, nhưng requests tổng có thể lệch mạnh hơn.
- Một nhóm nhỏ LWT `IF revision = ?` để đo CAS contention **riêng**, không cộng với writes không điều kiện.
- Một nhóm late-arrival updates vào partition thời gian cũ để đánh giá TWCS/compaction behavior.

Sử dụng **tỷ lệ có thể giải thích được** và đo lại ngay tại generator/DB. Nếu UPDATE và INSERT cùng row cùng timestamp CQL tùy ý, last-write-wins có thể không đúng thứ tự test mong đợi; khi test time series, đừng mặc định arrival order chính là write timestamp order.

### 8.4. UPDATE có thể làm tăng tombstone pressure

Khi thay giá trị non-null bằng NULL, Cassandra tạo deletion marker. Một PATCH không có field nhưng serializer lại bind NULL thay vì UNSET có thể tạo tombstone “không đáng có”. Bộ test phải thể hiện:

~~~text
update_existing_non_null -> new_non_null
update_existing_non_null -> NULL (delete column)
update_with_UNSET         -> giữ nguyên cột
DELETE entire row         -> row tombstone
expire_by_TTL             -> TTL-based tombstone
~~~

Đo riêng các nhóm; chúng có ảnh hưởng khác nhau tới read latency/compaction và không thể rút gọn thành một con số “writes/s”.

### 8.5. Hỗn hợp read/write tạo ra áp lực khác prefill một chiều

Trong run hỗn hợp, inserts/updates làm memtable flush, SSTable count và compaction thay đổi **trong khi SELECT đang đọc**. Một run 100% writes sau đó mới chạy 100% reads không tương đương một run có reads & writes đồng thời.

Nên có:

1. **Read-only profile** trên dataset đã prefill.
2. **Write-only profile** để đo ingestion ceiling.
3. **Mixed realistic profile** theo tỷ lệ và skew thực.
4. **Mixed + fault profile** khi một replica/net link bị lỗi.

So sánh có thể giải thích điều gì; không dùng throughput của read-only để suy throughput của mixed load.

## 9. Read patterns phải dùng cùng phân phối dữ liệu

### 9.1. Bốn loại SELECT quan trọng

| Kiểu đọc | CQL minh họa | Chi phí và điều cần mô phỏng |
|---|---|---|
| Point lookup | `WHERE device_id=? AND event_day=? AND event_time=? AND event_id=?` | Exact clustering row, thường ít bytes |
| Latest-N | `WHERE device_id=? AND event_day=? LIMIT 100` | Mức locality khi phân vùng có clustering DESC |
| Range trong ngày | `WHERE ... AND event_time>=? AND event_time<?` | Số rows và page count thay đổi lớn |
| Read miss | `WHERE device_id=? AND event_day=?` nhưng partition không có | Bloom filters/index; có thể khác read hit |

**Không** tạo một profile 50% SELECT nhưng mọi SELECT chỉ lấy một row “vừa ghi” nếu hệ thống thật có range reads theo lịch sử, read misses, cache misses và pagination.

### 9.2. Recency của reads ảnh hưởng cache

Giả sử 80% đọc các event trong 48 giờ gần nhất:

- 60% SELECT truy cập các partitions mới nhất (thường được đọc nhiều).
- 20% range queries vào partitions vài ngày trước.
- 15% point queries vào historical data.
- 5% miss/negative lookups.

Đây là tỷ lệ minh họa để **phân rã 100% READ operations**, không phải tỷ lệ trên tổng requests. Nếu kết hợp với 55% read share toàn workload, phải nhân điều kiện đúng khi tổng hợp.

### 9.3. Paging thay đổi độ trễ và độ lớn response

~~~sql
SELECT event_time, event_id, payload
FROM load_lab.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 1000;
~~~

Nếu Java Driver dùng `pageSize=100` và query có 1.000 rows, việc tiêu thụ toàn bộ result có thể phát sinh nhiều page requests. Tỷ lệ queries **đọc tới cuối** và queries **chỉ đọc trang đầu** phải được mô phỏng đúng. Một test chỉ gọi `session.execute` rồi **không iterate results** không đo được cost của consumer đi qua toàn bộ pages.

`pageSize=100` là page-size target, **không** là cam kết chính xác 100 rows/page hoặc tổng 100 rows/query. Read với nhiều tombstones có thể trả ít live rows mà vẫn scan nhiều cells.

### 9.4. Negative reads và data age

Nếu phần lớn reads hỏi về event đã TTL-expire, tỷ lệ hit/miss thay đổi trong quá trình test. Một workload đọc lịch sử 30 ngày trên bảng retention 7 ngày có thể tạo nhiều misses; đó là workload nghiệp vụ khác với “80% đọc 48h” nên cần ghi rõ và phân bố theo profile.

**Mọi SELECT trong load run phải có phân phối key/bucket tương thích với dataset đã prefill**. Nếu SELECT dùng random UUID không trùng keys đã nạp, benchmark sẽ đo đa phần misses mà vẫn có thể có throughput rất cao.

## 10. Sinh dữ liệu tái lập: seed, identity và entropy

### 10.1. Manifest cần có trước khi tạo dữ liệu

Một manifest **minh họa**, không nhất thiết là file cấu hình của công cụ cụ thể:

~~~yaml
dataset_version: "load-lab-v1"
seed: 20261121
schema_version: "events_by_device_day-v1"
device_count: 200000
event_count: 1000000
hot_device_fraction: 0.01
hot_request_share: 0.40
day_start_utc: "2026-11-01"
days: 20
payload_mix:
  small_128_512_bytes: 0.55
  medium_1024_4096_bytes: 0.35
  large_8192_32768_bytes: 0.10
ttl_write_mix:
  none: 0.20
  seven_days: 0.60
  thirty_days: 0.20
operation_mix:
  read: 0.55
  insert: 0.25
  update: 0.15
  delete: 0.05
~~~

Thêm vào manifest thực: commit/build hash generator, Cassandra/Java Driver versions, RF/CL/DC, compaction/compression options, client threads, rate, start/end times, prefill steps, test phase và faults. **Không** ghi credentials, access tokens hoặc raw production keys.

### 10.2. Seed giúp tái lập, nhưng không tự làm kết quả y hệt

Cùng PRNG seed tạo lại **chuỗi lựa chọn logic** nếu code và thứ tự gọi RNG không đổi. Nhưng Cassandra thực thi phân tán, background compaction, GC, OS scheduling và placement của token/vnodes vẫn khiến p99 thay đổi giữa runs. Vì vậy:

- Dùng seed cố định cho dữ liệu và workload để so A/B.
- Phân biệt **row IDs** cố định với **workload arrival order** có thể random.
- Không dùng `UUID.randomUUID()` ở giữa code deterministic mà không ghi nó.
- Trong chạy song song, phân vùng seed theo worker/partition và bảo đảm các workers **không trùng khóa ngoài ý muốn**.
- Lưu thống kê **đã tạo thực** để kiểm chứng manifest; seed không chứng minh phân phối đã đúng.

### 10.3. Tạo UUID deterministic cho device và event

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

static UUID stableDeviceId(long seed, int index) {
    String key = "load-device:" + seed + ":" + index;
    return UUID.nameUUIDFromBytes(
        key.getBytes(StandardCharsets.UTF_8));
}

static UUID stableEventId(long seed, long sequence) {
    String key = "load-event:" + seed + ":" + sequence;
    return UUID.nameUUIDFromBytes(
        key.getBytes(StandardCharsets.UTF_8));
}
~~~

`UUID.nameUUIDFromBytes` là UUID deterministic từ bytes, phù hợp **synthetic fixture identity**. Không lấy nó làm UUID bảo mật/secret hoặc giả định key có thể “ẩn danh hóa” production identifiers an toàn. UUID v3/name-based phân tán trên token hash đủ tốt cho lab này, nhưng phải đo token ranges và đặc tính PRNG thực.

### 10.4. Payload generator với các entropy classes

~~~java
import java.util.Arrays;
import java.util.SplittableRandom;

static int choosePayloadSize(SplittableRandom rng) {
    double r = rng.nextDouble();
    if (r < 0.55) {
        return rng.nextInt(128, 513);
    } else if (r < 0.90) {
        return rng.nextInt(1024, 4097);
    }
    return rng.nextInt(8192, 32769);
}

static byte[] syntheticPayload(SplittableRandom rng, int size) {
    byte[] out = new byte[size];
    double kind = rng.nextDouble();

    if (kind < 0.10) {
        // Low entropy: rất dễ nén.
        Arrays.fill(out, (byte) 'A');
    } else if (kind < 0.50) {
        // Medium entropy: một từ điển ngẫu nhiên 64 bytes lặp.
        byte[] dictionary = new byte[64];
        rng.nextBytes(dictionary);
        for (int i = 0; i < size; i++) {
            out[i] = dictionary[i % dictionary.length];
        }
    } else {
        // High entropy: ít compressible hơn.
        rng.nextBytes(out);
    }
    return out;
}
~~~

Ở đây entropy mix là **10% low, 40% medium, 50% high** (tương ứng bảng profile bên trên). Đây là *synthetic approximation*, không phải JSON thật. Nếu service xử lý JSON/Avro/Protobuf, phải thêm đường encode/decode thật vì payload blob random không đo được JSON parsing, allocation và canonicalization cost.

### 10.5. Sinh event_time và bucket nhất quán

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.SplittableRandom;

static LocalDate chooseDay(SplittableRandom rng) {
    return LocalDate.of(2026, 11, 1)
        .plusDays(rng.nextInt(20));
}

static Instant chooseTimeInsideDay(
        SplittableRandom rng, LocalDate day) {
    return day.atStartOfDay(ZoneOffset.UTC)
        .toInstant()
        .plusSeconds(rng.nextLong(86_400));
}
~~~

Với generator này, `event_day` phải khớp `event_time` theo UTC. Nếu production dùng device-local timezone/day bucket, cần mô phỏng timezone/DST theo business rule thực; không chuyển UTC sang local date tùy tiện làm thay partition key.

**Lưu ý TTL:** đây chỉ là “ngày được ghi trong event”. Khi chạy generator hôm nay, TTL vẫn bắt đầu ở **thời điểm INSERT mới**, không từ 1–20/11/2026.

## 11. Java Driver 4.x: prefill mẫu có TTL cohorts

### 11.1. Prepared statements cho TTL/no-TTL

Một INSERT có TTL cần CQL statement có `USING TTL ?`; bản không TTL dùng statement khác. Không dùng TTL=0 để đại diện cho “hàng đã hết hạn”.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.nio.ByteBuffer;
import java.time.Instant;
import java.time.LocalDate;
import java.util.SplittableRandom;
import java.util.UUID;

static void prefillDemo(CqlSession session,
                        long seed, int events, int deviceCount) {
    String columns = "(device_id,event_day,event_time,event_id," +
                     "payload,event_type,status)";
    String values = " VALUES (?,?,?,?,?,?,?)";
    String prefix = "INSERT INTO load_lab.events_by_device_day " +
                    columns + values;

    PreparedStatement noTtl = session.prepare(prefix);
    PreparedStatement withTtl = session.prepare(
        prefix + " USING TTL ?");

    SplittableRandom rng = new SplittableRandom(seed);
    int hotCount = Math.max(1, deviceCount / 100);

    for (int sequence = 0; sequence < events; sequence++) {
        int deviceIndex = chooseDeviceIndex(rng, deviceCount, hotCount);
        UUID device = stableDeviceId(seed, deviceIndex);
        LocalDate day = chooseDay(rng);
        Instant eventTime = chooseTimeInsideDay(rng, day);
        UUID eventId = stableEventId(seed, sequence);
        byte[] bytes = syntheticPayload(rng, choosePayloadSize(rng));

        double ttlClass = rng.nextDouble();
        BoundStatement stmt;
        if (ttlClass < 0.20) {
            stmt = noTtl.bind(device, day, eventTime, eventId,
                ByteBuffer.wrap(bytes), "telemetry", "NEW");
        } else {
            int ttlSeconds = ttlClass < 0.80
                ? 7 * 86_400 : 30 * 86_400;
            stmt = withTtl.bind(device, day, eventTime, eventId,
                ByteBuffer.wrap(bytes), "telemetry", "NEW",
                ttlSeconds);
        }

        session.execute(stmt
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(false));
    }
}
~~~

**Giới hạn rõ:** hàm này là **generator prefill minh họa, đồng bộ, chạy tuần tự** để thấy schema/TTL/cohorts; **không phải load generator đạt QPS cao**. Nó chưa đảm bảo histogram rows/partition p50=12/p99=1.000, vì phân phối ngẫu nhiên device/day có thể tạo profile khác. Khi cần fidelity cao, phải **phân bổ số rows cho từng partition từ histogram mong muốn trước**, sau đó mới tạo rows theo quota; cuối cùng đo thực tế và điều chỉnh.

Đoạn demo dùng `setIdempotent(false)` một cách thận trọng: dù INSERT có primary key/payload cố định, **TTL khiến replay sau timeout có thể kéo dài thời gian lưu giữ**, làm nó không idempotent theo retention deadline. Với prefill yêu cầu expiry tuyệt đối, hãy dùng operation IDs, lưu deadline/remaining TTL và policy retry có kiểm soát. Nếu bài thử muốn đo đúng hành vi replay của application, chọn flag theo semantics thực thay vì sao chép từ demo.

### 11.2. Kiểm tra đủ dữ liệu trước khi chạy workload

Sau prefill:

~~~sql
SELECT event_time, event_id, event_type, status
FROM load_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Địa chỉ device UUID trên chỉ là mẫu; generator deterministic ở trên **không bảo đảm tạo đúng UUID này**. Với test thực, lấy device/day **từ manifest hoặc tập key mà generator đã ghi**, không lấy một UUID minh họa rồi kết luận nạp dữ liệu lỗi vì query empty.

Kiểm chứng:

- Tổng successful inserts và errors của client.
- Số distinct partition keys thực (có thể lấy qua một sample/index riêng; tránh full table scan production).
- Histogram payload bytes **ở phía generator** và compressed SSTable footprint phía Cassandra.
- Tỷ lệ records có TTL/null TTL bằng sampling trong key catalog.
- Không có keys “update-only” ngẫu nhiên chưa từng tạo.
- Nút local replicas Up, schema agreement và RF/CL đúng.

### 11.3. Chuyển từ prefill sang generator nhiều worker

Để load thật:

1. Chia range `sequence` hoặc partition-key catalog thành các shard không giao nhau.
2. Mỗi worker dùng seed derived từ master seed + worker index một cách deterministic.
3. Dùng `executeAsync`/bounded concurrency thay vì một `session.execute` tuần tự; **không** tạo unbounded futures.
4. Áp open-loop target arrival rate nếu muốn đo response khi hệ thống quá tải; theo dõi offered vs achieved QPS.
5. Gắn deadline/request timeout, idempotency và **không retry độc lập qua nhiều tầng**.
6. Ghi success/timeout/error, completed bytes và partition histograms theo phase.
7. Khi một worker bị cancel vì deadline, ghi mutation outcome **UNKNOWN** nếu có thể đã gửi đến Cassandra.

**Không dùng một session mới cho mỗi record**. Java Driver `CqlSession` dài hạn, prepared statements được reuse, không log mỗi payload hoặc query value. Bounded queue/throttling và token-aware routing giúp workload runner không tự trở thành bottleneck.

## 12. cassandra-stress user mode và giới hạn mô hình

Apache Cassandra cung cấp `cassandra-stress` với **user mode**: profile YAML mô tả schema, phân phối các cột, custom SELECT queries và operation weights. Nó phù hợp để xác định baseline/tải sơ bộ trên một schema, nhưng **không tự mô phỏng hoàn chỉnh** mọi business workflow hoặc tuổi TTL.

### 12.1. Profile phác thảo cho events_by_device_day

Ví dụ định dạng để minh họa cách khai báo; cần đối chiếu `cassandra-stress help user` và bản công cụ thực trước khi dùng:

~~~yaml
specname: realistic_events
keyspace: load_lab
table: events_by_device_day

columnspec:
  - name: device_id
    population: uniform(1..200000)
  - name: event_day
    population: uniform(1..20)
  - name: event_time
    cluster: gaussian(1..1000,3)
  - name: payload
    size: gaussian(128..32768,8192)

queries:
  latest:
    cql: SELECT event_time, event_id, event_type, status
         FROM events_by_device_day
         WHERE device_id = ? AND event_day = ? LIMIT 100
    fields: samerow
~~~

Đây là **profile khởi đầu để học cấu trúc**, không cam kết hoàn toàn chạy nguyên văn trên mọi cassandra-stress release: generator của các CQL types `date`/`uuid` và trường `cluster` có thể phụ thuộc version/constraints. Kiểm tra schema thật, codec và values được sinh. Một phân phối `gaussian(128..32768,8192)` có trọng số khác **mix ba nhóm 55/35/10** đã định nghĩa; muốn đúng histogram, cần nhiều profiles/runner tùy biến hoặc generator Java.

**Không có `USING TTL` trong INSERT implicit của ví dụ**, nên profile này không tái hiện TTL cohorts hay cập nhật theo tuổi trừ khi bạn bổ sung workflow/phần mềm khác. Đừng báo kết quả “TTL realistic” chỉ từ profile này.

### 12.2. Chạy user mode với weights minh họa

~~~bash
# CHỈ trên CLUSTER LAB. Không dùng truncate=once trên dữ liệu cần giữ.
cassandra-stress user profile=./realistic-events.yaml duration=10m \
  "ops(insert=3,latest=7)" -node 10.0.0.11 -rate threads=20
~~~

Các weights trên là 30% INSERT / 70% SELECT **trong operation mix của tool**, không phải business workload 55% SELECT / 25% INSERT / 15% UPDATE / 5% DELETE. `cassandra-stress user` có cách riêng để xác định insert/query operation, batch và key reuse; phải kiểm tra output operations thực. Lệnh không dùng `truncate=once` vì đó là tùy chọn **phá hủy dữ liệu của table lab**.

Nếu cần UPDATE/DELETE/CAS theo existing keys, TTL cohorts và temporal locality phức tạp, runner Java hoặc NoSQLBench/custom workload script đã được review thường phù hợp hơn. Dù dùng công cụ nào, hãy báo **observed op mix** thay vì coi weights trong YAML là bằng chứng đủ.

### 12.3. Những sai lệch thường gặp của công cụ stress

| Sai lệch | Triệu chứng | Cách kiểm tra |
|---|---|---|
| Tool sinh đều key, ứng dụng skew mạnh | QPS benchmark quá tốt | Top-k key share |
| Tool INSERT trong batches, ứng dụng ghi từng row | Write overhead/batch latency khác | Batches/op, partitions/batch |
| Tool tạo rows mới thay vì updates | Partition count tăng | Delta partition/row count |
| Tool không đặt TTL | Tombstones thấp giả | TTL sample, expired cohort |
| Tool chỉ query hot rows đã cache | Read p99 thấp giả | Read age, misses, SSTables/read |
| Tool nén payload quá tốt | Disk/IO nhỏ giả | Compression ratio theo dữ liệu thật |
| Tool chỉ đo duration ngắn | Không thấy compaction/aging | Run dài hơn, pre-aged dataset |
| Tool ném hết dữ liệu vào một DC | Khác routing/WAN thật | Session local DC, coordinator metrics |

### 12.4. Bổ sung model khi không thể mô tả bằng một YAML

Có thể chia nhiều phases và tools:

~~~text
Tool A: prefill schema + rows/partitions profile có seed
Tool B: aged TTL/deletes với timeline rõ
Tool C: mixed reads/inserts/updates/deletes theo existing-key catalog
Tool D: fault orchestrator (chỉ trên cluster được phép)
Tool E: metrics collector + workload fidelity validator
~~~

Chúng có thể là một chương trình thống nhất, nhưng **cùng dùng manifest/run_id, cùng clock timeline và cùng ID catalog**. Nếu prefill dùng device IDs khác load runner, benchmark sẽ đo misses/upserts thay vì workload dự kiến.

## 13. Prefill, aging, steady-state: thứ tự chạy quyết định kết quả

### 13.1. Vì sao cần prefill trước khi đo?

Một hệ thống Cassandra mới khởi tạo chưa có SSTables lịch sử, compaction overlap hay expired cells. Nếu gửi UPDATE và SELECT ngay, khả năng cao:

- UPDATE chạm keys **chưa tồn tại** nên là upserts.
- SELECT chủ yếu trả misses.
- Caches mới, có thể khác so với hot cache khi đã hoạt động.
- Chưa có tombstones do TTL hết hạn hoặc DELETE có tuổi.
- Disk/compaction backlog chưa phản ánh steady state.

Do đó phải tạo **một bộ dữ liệu đủ lớn để các đường đọc/ghi có đối tượng thực**, đồng thời đủ thời gian cho các trạng thái nền sinh ra. Prefill chỉ là bước đầu, **không phải toàn bộ load test**.

### 13.2. Một timeline có thể tái lập

| Pha | Nội dung | Cần lưu lại |
|---|---|---|
| **P0 — Validate** | Kiểm tra schema, RF/CL/DC, node health, dung lượng trống, seed | Cluster/version/manifest |
| **P1 — Prefill** | Nạp partitions, rows/payload/TTL theo phân phối mục tiêu | Successful rows, key catalog, histograms |
| **P2 — Aging** | Tạo deletes/updates/TTL cohorts và để thời gian thật trôi | TTL còn lại, tombstones, SSTable count |
| **P3 — Warm-up** | Đọc/ghi với nhịp nhỏ để ổn định cache/JIT/connection | Cache hit, compaction, latency trend |
| **P4 — Baseline** | Đo mixed workload không fault, rate ổn định | QPS, p50/p95/p99, errors, resource |
| **P5 — Fault** | Cùng offered workload, inject một lỗi có kiểm soát | Sự kiện fault chính xác, errors, availability |
| **P6 — Recovery** | Gỡ fault, giữ tải để đo hồi phục | Hints, repair/compaction, p99 recovery |
| **P7 — Verify** | Kiểm tra state cuối, fidelity, missing/duplicate effects | Acceptance report, run artifacts |

Không nhất thiết cho mọi pha một số phút cố định. **Độ dài pha** phụ thuộc TTL/compaction time horizon và SLO thực. Một bài lab 20 phút với TTL 90 s có thể thể hiện cơ chế expiration; nó **không** thay cho soak nhiều ngày nếu production retention 30 ngày.

### 13.3. Warm-up không được xóa trạng thái mà cần đo

Có thể warm connection pools, JIT và cache trước khi lấy baseline. Nhưng nếu benchmark mục tiêu là **cold-start/recovery**, warm-up có thể che đi vấn đề. Nên chạy hai thí nghiệm rõ:

- **Cold-ish state:** cluster được khởi động/khôi phục theo kịch bản, thống kê trước khi warm.
- **Warm steady state:** có traffic và cache đủ lâu, lưu baseline trước fault.

Không gọi `nodetool flush`, major compaction, truncate hoặc restart node một cách tùy tiện giữa các runs vì chúng thay SSTable layout, cache và disk. Nếu dùng các thao tác này như một biến thí nghiệm, ghi nó thành phase riêng và chỉ làm trên cluster lab.

### 13.4. Làm già dữ liệu mà không “du hành thời gian” sai

Ba cách hợp lý, theo chi phí:

1. **Soak thật qua thời gian:** nạp TTL mix, UPDATE/DELETE hàng ngày/giờ, theo dõi SSTables & tombstones. Fidelity cao nhất với vòng đời thực, nhưng tốn thời gian.
2. **Bản sao lab đã có lịch sử:** phục hồi snapshot/data volume **từ môi trường lab được phép và cùng version/topology phù hợp**, đảm bảo không có PII; kiểm chứng repair/ownership/metadata trước khi đo.
3. **TTL ngắn để mô phỏng cơ chế:** dùng 30/90/300 s, chờ các cohorts hết hạn và quan sát. Dễ tái lập nhanh, nhưng **không tương đương** 7/30 ngày về compaction, repair và aging SSTable.

**Không** giả lập tuổi tombstone bằng việc chỉ đặt `event_time` trong CQL lùi 90 ngày. Trường dữ liệu đó khác timestamp ghi/TTL và không khiến SSTables có lịch sử tuổi thật. Tránh tự sửa system clock của một node hoặc thao tác file SSTables sản xuất để “tạo tuổi” vì dễ làm sai semantics và an toàn cluster.

### 13.5. Khi giữ target QPS, dataset vẫn thay đổi

Ở workload mixed, INSERT tăng số rows/partitions, DELETE/TTL làm giảm live cells, UPDATE tạo versions mới, compaction thay disk layout. Một run 6 giờ với target 5.000 ops/s **không phải test một dataset tĩnh**.

Phải tính:

~~~text
estimated net live row growth =
    new_key_inserts
    - whole_row_deletions
    - rows becoming fully expired
    + reinserted/previously missing rows

estimated logical cell churn =
    cells updated + cells expired + cells deleted
~~~

Hai đại lượng cần được đo thực, không dựa tuyệt đối vào công thức vì Cassandra dùng liveness markers, cell-level TTL và timestamps. Nếu cần A/B compaction trên cùng starting state, dùng snapshot/recreate **có kiểm chứng** để tránh dataset drift làm nhiễu kết quả.

## 14. Fault testing với dữ liệu giống nhau trước và sau lỗi

### 14.1. Fault injection không thay thế workload fidelity

Một run mất node trên 1.000 keys đều, không TTL không UPDATE sẽ đo khả năng vượt lỗi **của workload đó**, không chứng minh hệ thống chịu được mất node khi hot keys dồn lên một replica set hoặc tombstone scans tăng sau 30 ngày.

Để so baseline với fault:

- **Cùng schema/RF/CL/compaction/compression** (trừ biến được thử).
- Cùng dataset seed hoặc starting snapshot.
- Cùng phân phối hot/cold và query types theo phase.
- Cùng target offered QPS và cùng mức concurrency/backpressure.
- Cùng rules về timeout/retry/idempotence.
- Chỉ thay **một fault chính** trong một thí nghiệm đơn, rồi mở rộng sang combined faults có ghi nhãn.

### 14.2. Ma trận lỗi cho lab RF=3, một DC

| Lỗi thử | Điều kiện | Điều nên quan sát | Không được kết luận |
|---|---|---|---|
| Một node dừng | RF3, local DC có 3 nodes, CL=LOCAL_QUORUM | Availability, coordinator shifts, p95/p99, hints, backlog | “Không bao giờ có timeout” |
| Network latency tới một replica | Có proxy/network emulator trong lab | Read latency distribution, retry/speculation, queue | Một ping RTT đủ đại diện CQL |
| Packet loss ngắn | Traffic và fault window rõ ràng | Driver timeouts, unknown writes, recovery | Timeout = mutation chưa commit |
| Disk IO throttling một node | Có kiểm soát throughput/latency, disk còn headroom | Flush/compaction backlog, GC, p99 | Chỉ xem client QPS là đủ |
| Compaction backlog | Ingestion/update/TTL phù hợp | Pending compactions, SSTables/read, disk used | Một lần major compaction “sửa benchmark” |
| Burst TTL expiration | Cohorts hết hạn cùng thời điểm | Tombstone scan, read p99, disk reclaim lag | TTL expired = bytes đã được trả ngay |
| Hot-key burst khi lỗi | Các keys có replica overlap đáng kể | Per-node skew, client errors | Uniform key load phản ánh điều này |

**Không thực hiện fault injection trên production** nếu không có runbook/chấp thuận/rollback rõ ràng. Cách an toàn nhất là cluster test riêng với quyền dừng/khôi phục các node và ngân sách disk/network riêng.

### 14.3. RF3 + LOCAL_QUORUM không có nghĩa mọi lỗi đều “êm”

Trong một DC RF=3, LOCAL_QUORUM cần **hai replica responses** theo quy tắc CL. Khi một replica down, lý thuyết hai replica còn lại có thể đáp ứng, nhưng:

- Coordinator có thể chưa cập nhật trạng thái node Down.
- Một trong hai replica còn lại có thể chậm/quá tải.
- Driver có thể retry coordinator khác theo policy giới hạn.
- Hints/repair và compaction có thể tạo recovery load.
- In-flight writes lúc network bị đứt có thể có **unknown outcome**.

Vì vậy báo **actual availability/timeouts**, không dùng công thức quorum để khẳng định zero errors. Nếu chỉ có RF1/1 node, tắt node tất nhiên làm mất khả năng đọc/ghi — đó **không** phải thí nghiệm fault tolerance RF3.

### 14.4. Đo khả năng hồi phục sau khi bật node lại

Ghi mốc:

~~~text
t0  baseline ổn định
t1  inject fault
t2  fault được phát hiện ở client/driver/cluster
t3  fault được gỡ
t4  cluster nodes Up/Normal theo trạng thái cần thiết
t5  offered QPS và p99 đạt tiêu chí hồi phục trong thời gian liên tục
t6  dữ liệu/repair/hints/compaction đạt điều kiện integrity/recovery
~~~

**t4 ≠ t6**: `nodetool status` báo node Up chưa chứng minh mọi replica đã cùng dữ liệu; cần quan sát hints, repair state, consistency checks và workload outcome theo runbook phù hợp. Đo **time-to-recover** ở cả client SLO lẫn data integrity.

### 14.5. Kiểm chứng đúng dữ liệu khi có retry

Nếu UPDATE là “set status='ACTIVE'” với timestamp nhất quán, retry có thể chấp nhận hơn counter increment/list append; nhưng TTL và concurrent writes vẫn làm semantics phức tạp.

Với fault injection:

- Gắn `operation_id`/request ID để đối chiếu intended vs observed transitions.
- Tách `SUCCESS`, `FAILED`, `UNKNOWN_TIMEOUT`.
- Không coi một timeout là rollback.
- Không biến LWT `wasApplied=false` thành network error cần retry.
- Đếm duplicate inserts/side effects và lost updates bằng kiểm tra key catalog sau recovery.
- Dùng consistency được yêu cầu; không tự hạ CL để dashboard ít lỗi.

Tập dữ liệu đại diện phải có đủ updates/TTL để **làm lộ các lỗi idempotency** mà test chỉ INSERT mới không bắt gặp.

## 15. Quan sát đúng cả driver và Cassandra

### 15.1. Dashboard tối thiểu

| Nơi thu | Metric | Vì sao cần |
|---|---|---|
| Load generator | Offered operations/s vs completed/s | Phát hiện tool không tạo đủ tải khi backend chậm |
| Load generator | Operation mix thực: read/insert/update/delete | Xác minh profile |
| Load generator | p50/p95/p99 end-to-end, timeout, error codes | Thấy tail latency và failures |
| Load generator | Read-hit/update-target-hit, rows/op, bytes/op | Không đo nhầm misses/upserts |
| Driver | Requests, retries, speculative executions, inflight, pool saturation | Phân biệt số business requests và actual CQL executions |
| Cassandra Table metrics | EstimatedPartitionSizeHistogram, EstimatedColumnCountHistogram | Đo chiều rộng/tổng thể partitions |
| Cassandra Table metrics | TombstoneScannedHistogram, TombstoneWarnings, TombstoneFailures | Đo áp lực TTL/deletes |
| Cassandra Table metrics | SSTablesPerReadHistogram, ReadLatency, WriteLatency | Read amplification/local response |
| Cassandra Table metrics | LiveDiskSpaceUsed, TotalDiskSpaceUsed, CompressionRatio | Capacity/SSTables & compression |
| Cassandra | PendingCompactions, PendingFlushes, CPU, GC, disk IO/network | Background workload và overload |
| Cluster | Node Up/Down, hints, repair/recovery progress | Tách detection và recovery |

Tên metrics có thể khác giữa Cassandra 4.x/5.x và exporters. Các Table metrics kể trên được mô tả trong tài liệu Apache Cassandra, nhưng phải kiểm tra exporter mapping thực và đơn vị đo. Cassandra JMX thường **mỗi node có metric riêng**; dashboard cluster phải tổng hợp có ý thức, không cộng p99 node-level như counter.

### 15.2. Công cụ kiểm chứng

Trên **lab**:

~~~bash
nodetool status
nodetool tablestats load_lab.events_by_device_day
nodetool tablehistograms load_lab events_by_device_day
nodetool tpstats
nodetool compactionstats
~~~

Một số phiên bản còn có `nodetool toppartitions` để lấy mẫu hot partitions; `sstablemetadata`/`sstablepartitions` giúp xem các đặc tính dữ liệu **ở cấp SSTable** khi được chạy theo quy trình phù hợp và đủ quyền. Những tools đó có thể tác động IO hoặc đòi đúng file/định dạng theo bản Cassandra; **không chạy scan toàn disk trong lúc đang đo tải** rồi coi kết quả không bị nhiễu.

`nodetool tablehistograms` cung cấp estimated distribution của partition size, cell count, SSTables per read và latency; không nên coi percentiles **xấp xỉ** là số liệu chính xác đến từng byte. Kết hợp với histogram phía generator và sampled CQL verification.

### 15.3. Tên “CompressionRatio” không đủ để kết luận dung lượng

Một bảng có compression ratio đẹp chưa chắc ít tombstones hoặc compaction work. Cần đo **cả**:

~~~text
payload bytes generated
logical live cells / rows estimated
SSTables live disk bytes
total disk bytes including obsolete SSTables
snapshot disk bytes / backup overhead
commitlog volume & flush counts
compression ratio
read p99, SSTables per read, tombstones scanned
~~~

Nếu bật snapshots/incremental backups, disk usage khác “LiveDiskSpaceUsed” của bảng; phải ghi backup policy trong manifest. Không dùng một tỷ lệ nén đo từ 1.000 rows đồng dạng để dự đoán hàng trăm GB payload có entropy khác.

### 15.4. Đo tail latency mà không che lỗi

Báo:

- p50/p95/p99/p99.9 latency **của successful requests**.
- Error/timeout rates và time-to-failure **riêng**, không thả exceptions ra khỏi histogram rồi chỉ khoe p99 đẹp.
- Offered vs achieved throughput để nhận diện load generator bị **closed-loop throttling** khi cluster chậm.
- Per-operation/class p99: latest-read, range-read, insert, update, delete, LWT khác nhau.
- Số replicas/coordinator reroutes, hotset skew và disk queues.
- Rolling windows tương ứng fault injection t0–t6, không chỉ trung bình 30 phút che 5 phút outage.

## 16. Validation gates: tập dữ liệu sai thì run không hợp lệ

### 16.1. Data fidelity acceptance

Đặt ngưỡng **trước khi chạy**, căn theo cỡ mẫu/histogram. Ví dụ ngưỡng lab để thảo luận:

| Chỉ số | Target giả định | Gate minh họa |
|---|---:|---|
| Distinct devices generated | 200.000 | Kiểm đủ theo manifest nếu prefill đủ devices |
| Event rows | 1.000.000 | Tỷ lệ successful inserts/verification gần target |
| Payload bucket 128–512 B | 55% | Trong khoảng 53–57% |
| Payload bucket 1–4 KiB | 35% | Trong khoảng 33–37% |
| Payload bucket 8–32 KiB | 10% | Trong khoảng 9–11% |
| Hot 1% devices request share | 40% | Trong khoảng 38–42% |
| TTL none/7d/30d tại lúc ghi | 20/60/20% | Mỗi bucket sai lệch tối đa 2 điểm % |
| Read/Insert/Update/Delete requests | 55/25/15/5% | Trong khoảng sai lệch định trước theo cỡ mẫu |
| UPDATE targets là live rows | Gần 100% cho profile này | Đo hit ratio thật; báo mọi miss |
| Rows/partition p99/max | Theo histogram đã chốt | Sai lệch định trước; không dùng một mean |
| Disk compression và compaction | Được đo, không đoán | Ghi baseline/so sánh theo hardware và strategy |

Các gate **không phải tiêu chuẩn chung** của Cassandra. Với chỉ 100 requests, không thể đòi mỗi nhóm 5% khớp sai số 1% như khi có 10 triệu operations. Nếu profile yêu cầu **tất cả** 200.000 devices phải có event, generator chọn device ID ngẫu nhiên có thể **không thỏa điều đó** dù có 1 triệu events; phải cấp ít nhất một event mỗi device trước rồi mới thêm phân phối skew.

### 16.2. Phân phối thời gian phải được xác minh

Kiểm tra theo **phase và timestamp thực**:

~~~text
event_time distribution           : các ngày/giờ business
write_arrival_time distribution   : khi request được thực thi
TTL_seconds_at_write             : no TTL, 7d, 30d theo mix
remaining_TTL_at_baseline         : phân phối TTL còn lại thật
expired/deleted cell cohorts      : tuổi tombstone thực
update_age_delta                 : thời gian từ insert đến update
read_age_delta                   : thời gian từ ghi đến đọc
~~~

Nếu generator chỉ gán `event_time` trong quá khứ nhưng tất cả `remaining_TTL_at_baseline≈7days`, đó **không phải dataset đã có tuổi TTL**. Bài test fault vẫn có thể hợp lệ cho **fresh-data profile**, nhưng không được đặt nhãn “aged 30d TTL realism”.

### 16.3. Kết quả run phải có khả năng audit

Lưu dưới dạng manifest/summary **của hệ thống benchmark bên ngoài bài học**:

~~~yaml
run_id: "example-20261121-a"
profile_hash: "<checksum of approved profile>"
seed: 20261121
schema_version: "events_by_device_day-v1"
cassandra_version: "record-actual-version"
driver_version: "record-actual-version"
topology: "record-node-count-dc-rf-cl"
compaction: "record-actual"
compression: "record-actual"
warmup: "record-duration-and-traffic"
fault: "record-type-window-target-node"
fidelity_checks: "PASS-or-FAIL-with-reasons"
metrics_artifact: "path-to-run-report"
~~~

**Không ghi** một kết quả `PASS` vào báo cáo khi chưa chạy validator. Nếu fidelity gate fail, run vẫn có giá trị như một thí nghiệm **được ghi nhãn khác** (ví dụ “uniform microbenchmark”), nhưng không được công bố là “representative workload benchmark”.

### 16.4. Tách workload drift khỏi fault effect

Khi p99 tăng trong pha fault, so đồng thời:

1. Offered QPS và operation mix: có giữ nguyên không?
2. Hot-key share: có chuyển sang keys khác không?
3. Payload-size distribution: có spike >p99 trong fault không?
4. TTL/expired cohort: có đúng lúc burst expiration không?
5. Compaction/repair: backlog tăng vì workload trước đó hay do fault?
6. Replica availability/coordinator: thật sự liên quan fault được inject không?

Nếu cùng lúc target rate tăng gấp đôi và hotset chuyển, không thể kết luận **toàn bộ** thay đổi latency do dừng một node. Lặp thí nghiệm với từng biến độc lập trước khi thử sự kết hợp.

## 17. Bài thực hành: so ba bộ dữ liệu có cùng số hàng

### 17.1. Chuẩn bị lab

Sử dụng **cluster lab** và schema mục 4. Chuẩn bị ba datasets có **cùng tổng số rows logic** nhưng khác phân phối; dùng keyspace/table lab tách biệt hoặc tái tạo starting snapshot hợp lệ cho từng run. Không copy dữ liệu từ production.

| Dataset | Kích thước | Partition access | TTL/updates | Mục đích |
|---|---|---|---|---|
| **A — Uniform fresh** | 100% payload 1 KiB | Uniform, skinny | Không TTL, INSERT chủ yếu | Control/microbenchmark |
| **B — Representative** | Mix 55/35/10 như profile | Top 1% devices nhận ~40% requests | Mix TTL 20/60/20; 15% UPDATE, 5% DELETE | So sánh fidelity |
| **C — Adversarial** | 10% rất lớn + long tail rõ | Hotset nhỏ hơn, partitions rộng hơn | Burst TTL expiration, nhiều updates/delete | Tìm giới hạn khi gần worst-case |

**Đừng** đồng thời thay 5 biến rồi kết luận biến nào gây ảnh hưởng riêng. Dataset C là bài kiểm thử tổng hợp “stress boundary”; nếu muốn giải thích nguyên nhân, tạo các run A/B nhỏ hơn chỉ thay **một biến**: size, hotset, TTL hoặc update ratio.

### 17.2. Tạo baseline có định lượng

1. Kiểm tra `nodetool status`, version, keyspace RF và local DC.
2. Tạo schema ở mục 4 trên lab phù hợp; lấy `DESCRIBE KEYSPACE load_lab` kiểm tra CQL.
3. Tạo manifest và seed cố định.
4. Prefill dữ liệu có số rows và phân phối dự kiến; không báo PASS nếu chưa kiểm chứng histograms.
5. Nếu profile cần TTL aged, thực hiện pha aging theo thời gian thật hoặc chọn lab TTL ngắn đã ghi nhãn.
6. Chạy warm-up cùng arrival pattern, sau đó đo baseline một khoảng đủ dài để lấy tail latency có ý nghĩa.
7. Lưu per-node metrics, workload offered/achieved rates, op mix, errors, p95/p99 và compression/disk.

**Không** lấy một SELECT 10 lần rồi công bố p99 là benchmark. Cỡ mẫu phải đủ lớn, thời gian và workload đủ ổn định, độ trễ có error/timeout coverage rõ.

### 17.3. Thử hotset giữ QPS và data bytes gần như cũ

Giữ cùng payload distribution, TTL và op mix; chỉ đổi partition visitation:

~~~text
Run U: 200.000 devices được chọn đều
Run H: top 2.000 devices nhận 40% visits

Giữ offered QPS, CL, page size, driver timeout,
client concurrency và thời lượng phase giống nhau.
~~~

Ghi:

| Chỉ số | Run U | Run H | Ý nghĩa |
|---|---|---|---|
| Offered/achieved ops/s | _điền_ | _điền_ | Client có giữ target không |
| p95/p99 latest-read | _điền_ | _điền_ | Tác động hot partition |
| p95/p99 update | _điền_ | _điền_ | Contention trên hot keys |
| Errors/timeouts | _điền_ | _điền_ | SLO và tail health |
| Top 1% key request share | _điền_ | _điền_ | Validate skew thực |
| Per-node CPU/IO/queue | _điền_ | _điền_ | Replica-set hotspots |
| SSTables/read & tombstone scans | _điền_ | _điền_ | Tách scan khỏi skew |

Nếu p99 gần như không đổi, có thể cluster còn nhiều headroom, key hot không tập trung trên cùng replica sets, hoặc offered load chưa đủ cao. **Đừng** vội suy rằng “Cassandra không bị ảnh hưởng bởi hot partitions” chỉ từ một run.

### 17.4. Thử TTL và UPDATE một cách có kiểm soát

Chạy ba tình huống với cùng prefill size:

- **T0:** 0% TTL + 0% UPDATE/DELETE, chỉ thêm dữ liệu mới.
- **T1:** TTL mix nhưng không update, cho các cohorts gần hết hạn.
- **T2:** TTL mix + 15% UPDATE + 5% DELETE, bao gồm updates vào rows đã tồn tại và TTL đã cạn.

Không cần các tỉ lệ này phải bằng production; mục đích là **tách ảnh hưởng**. Đo p99, SSTables/read, tombstones scanned, pending compactions, live/total disk size, write bytes và read hit rate theo từng giai đoạn.

### 17.5. Thử lỗi node sau khi profile đạt gate

Trong cluster RF3/LOCAL_QUORUM lab:

1. Run baseline B và ghi cấu hình/metrics.
2. Inject **một node Down** đã chọn trong khoảng thời gian cố định; có runbook phục hồi.
3. Giữ target arrival rate và profile B, nhưng **không ép client retry vô hạn** khi node Down.
4. Đo unavailable/timeout, p99, offered vs completed ops, coordinator distribution.
5. Khôi phục node, theo dõi hints/repair/compaction và thời gian ổn định SLO.
6. Kiểm tra một mẫu các row đã insert/update/delete và các operations có timeout theo ledger.
7. Lặp với profile A để thấy **dataset realism ảnh hưởng tới kết quả fault test** như thế nào.

Nếu không có quyền gây lỗi trên cluster riêng, **không làm trên production**. Vẫn có thể hoàn thành các case phân phối, TTL và sizing trên lab một node; đánh dấu fault test **NOT_EXECUTED**, không bịa kết quả.

## 18. Sai lầm thường gặp và câu hỏi vận dụng

### 18.1. Bảng anti-patterns

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Chỉ đặt tổng rows, bỏ qua partition histogram | Bỏ sót wide partitions | Thiết kế rows/partition và max riêng |
| Random UUID cho từng read | Hầu hết là misses, benchmark “nhanh” giả | Key catalog trùng dữ liệu nạp |
| Uniform mọi keys | Che hot partitions/replica skew | Hot/cold, Zipf-like, bursts |
| Payload toàn số 0/`A` | Compression quá tốt | Mix entropy và đo disk thật |
| Payload toàn random bytes | Che JSON serialization và compression thật | Dùng distribution/encoding giống app |
| Chỉ INSERT, UPDATE không trúng keys | Không có churn/version history đúng | Update existing-key catalog |
| `event_time` cũ = TTL đã già | Sai: TTL bắt đầu lúc ghi | Soak/aged fixtures/short-TTL lab có ghi nhãn |
| TTL hết = disk free ngay | Tombstones/grace/compaction cần thời gian | Đo live/total disk và pending compaction |
| UPDATE mọi cột, trong khi app chỉ update status | Thêm IO/tombstones/TTL reset không đại diện | Mô phỏng partial mutations đúng |
| Không đo CANCEL/timeout/unknown writes | Số success giả và sai dữ liệu | Ledger, reconciliation, error breakdown |
| `truncate=once` khi không có môi trường cô lập | Có thể xóa dữ liệu ngoài ý muốn | Chỉ dùng destructive commands trên lab được xác minh |
| Bật GC/major compaction thủ công giữa runs | Mất tính so sánh của SSTable history | Cùng starting state, ghi mọi intervention |
| Chỉ đo một phút sau prefill | Không có TTL aging và steady-state | Warm-up/soak theo mục tiêu |
| Chỉ xem client p99 successful | Che timeouts/overload | Report error rate và offered vs achieved |
| RF1 một node dùng để khẳng định chịu node Down | Không kiểm tra replication | Multi-node RF3/CL phù hợp |
| Cùng lúc thay QPS, payload, hotset và fault | Không biết nguyên nhân | Single-variable A/B trước |

### 18.2. Bài 1 — hai workloads cùng số hàng

Hai bảng đều có 1 triệu rows. Bảng X có 1 row/partition; bảng Y có 10.000 rows/partition. Đội phát triển kết luận hai bảng có sức chịu tải tương đương. Có đúng không?

**Đáp án:** không. Token distribution, partition index, clustering range, tombstones và paging khác nhau đáng kể; cần histogram kích cỡ/rows/partition và đúng query pattern.

### 18.3. Bài 2 — 1 KiB toàn ký tự A

Một dataset 10 triệu rows, mỗi payload đúng 1 KiB toàn `A` cho compression ratio rất tốt. Đánh giá gì trước khi dùng kết quả để sizing production?

**Đáp án:** cần so payload entropy/format với dữ liệu thật, đo SSTable disk, bytes per row trên wire, metadata/replication và compaction overhead. Average payload bằng nhau chưa làm cost bằng nhau.

### 18.4. Bài 3 — TTL quá khứ

Ngày 21/11/2026, chạy INSERT `event_time='2026-10-01'` với `USING TTL 604800`. Hàng có “đã hết hạn từ lâu” không?

**Đáp án:** không. TTL mới được tính khi mutation được ghi, không theo event_time. Cần mô phỏng tuổi qua thời gian thật/fixtures đã già hoặc short TTL lab.

### 18.5. Bài 4 — UPDATE sai target

Test target 15% UPDATE nhưng mỗi UPDATE tạo UUID.randomUUID() và SET status. Vì sao số rows tăng mạnh?

**Đáp án:** Cassandra UPDATE là upsert; UUID mới thường chưa có. Phải dùng existing-key catalog, và đo update-target-exists share trên live dataset.

### 18.6. Bài 5 — top 1% keys

Top 1% keys nhận 40% requests. Có nghĩa 40% dung lượng disk nằm ở những keys đó không?

**Đáp án:** không. Request heat khác size; cần đo distribution bytes/partition và requests/partition riêng. Keys nhỏ vẫn có thể nóng.

### 18.7. Bài 6 — Hết TTL nhưng disk không giảm

Sau khi 50% rows hết TTL, disk usage vẫn chưa giảm tương ứng. Có phải TTL không hoạt động?

**Đáp án:** chưa chắc. Expired data trở thành tombstones; compaction chỉ reclaim khi thỏa điều kiện an toàn và SSTable layout phù hợp. Kiểm tra live reads, TTL() sample, tombstone metrics, repaired/unrepaired SSTables và compaction.

### 18.8. Bài 7 — Read-miss benchmark

Generator prefill 100.000 UUID, nhưng read sampler chọn ngẫu nhiên trên một không gian 128 bit không liên quan. Vì sao throughput đọc cao nhưng không đáng tin?

**Đáp án:** hầu hết là read misses; không đại diện latest-N/range/hit reads của ứng dụng. Cần keys trùng dataset và hit/miss mix đúng telemetry.

### 18.9. Bài 8 — Lỗi một replica

Cluster ba nodes RF3, LOCAL_QUORUM; một node Down. Vì sao client vẫn có thể nhận timeout dù hai node còn lại Up?

**Đáp án:** các replicas còn lại có thể chậm hoặc quá tải, coordinator membership/connection chưa ổn định, có network/GC/compaction. Quorum math không bảo đảm latency zero errors; đo thực và recovery.

### 18.10. Bài 9 — Lỗi phân tích p99

Sau fault, p99 successful requests giảm từ 90 ms xuống 70 ms nhưng timeout rate tăng từ 0% lên 20%. Có thể kết luận fault làm hệ thống nhanh hơn?

**Đáp án:** không. Histogram p99 chỉ còn các requests thành công; nhiều requests chậm bị timeout không được tính. Phải xét error rate, time-to-error, offered vs achieved throughput và SLO end-to-end.

### 18.11. Bài 10 — Tái lập nhưng dữ liệu sai

Hai lần dùng cùng seed, p99 khá giống nhau; tuy nhiên dataset được sinh không có bất kỳ partition nào >20 rows, trong khi profile yêu cầu p99=1.000 rows/partition. Run có đạt fidelity gate?

**Đáp án:** không. Reproducibility của *một dataset sai* không làm nó đại diện. Phải phân bổ rows theo partition histogram, rồi kiểm chứng trước khi load/fault test.

### Checklist trước khi công bố benchmark

- [ ] Có manifest/version/seed và phạm vi dữ liệu được phép dùng.
- [ ] Phân biệt logical payload, serialized CQL bytes, partition size và physical disk.
- [ ] Có p50/p95/p99/max rows/partition và bytes/partition, không chỉ tổng rows.
- [ ] Có hot keys/skew và đọc theo đúng partition/keyspace/bucket thật.
- [ ] Payload có distribution size và entropy, kiểm chứng compression ratio thực.
- [ ] TTL cohort phản ánh **thời điểm ghi/độ tuổi thật**, không chỉ event_time.
- [ ] Có các cohorts expired/tombstones và lịch sử compaction phù hợp mục tiêu.
- [ ] Update/delete target keys đã tồn tại, theo tỷ lệ có thể đo.
- [ ] Không gộp LWT, counter/list append và upsert thường thành một loại “UPDATE”.
- [ ] Có read miss/hit/range/latest-N, rows/op, pages/op, query recency đúng.
- [ ] Đã prefill, age, warm-up và lưu baseline **trước** fault.
- [ ] Fault injection chỉ trên lab được phép, có cửa sổ, rollback và stop conditions.
- [ ] Driver retries/speculative executions được đếm vào offered load thực.
- [ ] Ghi p95/p99 **cùng** error rate, unknown outcomes, offered/achieved QPS.
- [ ] Có Cassandra node/table metrics: tombstones, partition histograms, compaction, disk.
- [ ] Có validation gate so data/workload **thực tế** với manifest trước khi kết luận.
- [ ] So baseline/fault với cùng workload và starting state hoặc nêu rõ sai khác.
- [ ] Không khai báo PASS/điền số benchmark khi chưa thực sự chạy.

## 19. Tài liệu tham khảo

1. Apache Cassandra — [Cassandra Stress](https://cassandra.apache.org/doc/stable/cassandra/tooling/cassandra-stress.html): user mode, profile YAML, cột phân phối, query weights và cách chạy workloads.
2. Apache Cassandra — [Evaluating and refining data models](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/data-modeling_refining.html): tính toán partition cells/bytes và đánh giá wide partitions.
3. Apache Cassandra — [Data modeling introduction](https://cassandra.apache.org/doc/3.11/cassandra/data_modeling/intro.html): hướng dẫn lịch sử về partition size/cell count; phải đối chiếu release và workload.
4. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): tombstone, TTL, grace và logic xóa phân tán.
5. Apache Cassandra — [Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html): TTL, compaction, repaired/unrepaired SSTables.
6. Apache Cassandra — [TWCS](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/twcs.html): workload TTL/time-series, out-of-order writes và vấn đề expiry theo window.
7. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): EstimatedPartitionSizeHistogram, TombstoneScannedHistogram, SSTablesPerReadHistogram, compaction/disk metrics.
8. Apache Cassandra — [nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) và [Use nodetool](https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/use_nodetool.html): đo partition/read histograms và table health.
9. Apache Cassandra — [sstablemetadata](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablemetadata.html) và [sstablepartitions](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstablepartitions.html): dữ liệu/partition statistics trên SSTables khi dùng đúng quy trình.
10. Apache Cassandra Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/): prepared/bound statements, bind marker và immutable execution options.
11. Apache Cassandra Java Driver 4.19 — [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/) và [Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): page size/consumption, retry safety và thao tác có TTL.
12. Apache Cassandra — [CQL DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) và [CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): partition key, clustering, TTL, UPDATE/upsert, DELETE/LWT.
13. Oracle Java 17 — [SplittableRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/SplittableRandom.html): PRNG seed, split và `nextBytes` để sinh fixture.
