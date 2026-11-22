# Nạp dữ liệu bằng cqlsh COPY, sstableloader hoặc công cụ bulk phù hợp trong Apache Cassandra

> **Chương:** Di chuyển và schema  
> **Phạm vi:** Lựa chọn và vận hành phương án nạp dữ liệu vào Apache Cassandra theo định dạng nguồn (CSV/JSON, SSTable, dòng sự kiện), khối lượng, schema, partition key, topology đích, mức nhất quán đọc ghi và khả năng chịu tải. Bài dùng ví dụ CQL, lệnh CLI và Java Driver 4.x; cú pháp/flags của các công cụ thay đổi theo phiên bản, vì vậy luôn kiểm `--help` và tài liệu của binary triển khai.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **logical bulk load** (CSV/CQL mutations) với **physical SSTable streaming**, hiểu cách mỗi phương pháp ảnh hưởng timestamp, TTL, tombstone và replication.
2. Chọn giữa `cqlsh COPY FROM`, `sstableloader`, DataStax Bulk Loader (DSBulk), Spark Cassandra Connector, Java Driver và `nodetool import` theo dữ liệu nguồn, quy mô và yêu cầu nghiệp vụ.
3. Chuẩn bị keyspace/table theo **truy vấn và partition key**, kiểm type/primary key/UDT, RF theo datacenter và tránh hot/wide partitions trước khi nạp.
4. Viết ví dụ `COPY FROM/TO` với CSV có header, delimiter, NULL, UUID, timestamp; nhận diện lỗi quoting/encoding và các giới hạn của CSV.
5. Mô tả pipeline nạp SSTable từ snapshot/staging bằng `sstableloader`, cách nó lấy ring và stream đến natural replicas thay vì chạy `INSERT` cho từng hàng.
6. Thiết kế load theo đợt có rate limit, retry có kiểm soát, idempotency, checkpoint, dead-letter/quarantine và observability.
7. Thực hiện migration theo **backfill → catch-up → dual-write/CDC nếu cần → validation → cutover**, không ghi đè các mutation mới hợp lệ.
8. Kiểm nghiệm dữ liệu trên nhiều token ranges và datacenter bằng CQL, Java, metrics; biết khi nào phải dừng, rollback hay tiến hành sửa lỗi hướng tới trước.

Trong module **`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`**, Cassandra là **wide-column database phân tán**: partition key được băm thành token, replication strategy xác định replica, còn cách thiết kế bảng gắn trực tiếp với truy vấn. Nạp được một triệu dòng **không** chứng minh dữ liệu được chia đều, đọc hiệu quả hay nhất quán. Phải thiết kế đường nạp tương ứng **đường truy vấn và đường ghi** trước.

## 2. Hiểu ba kiểu dữ liệu đầu vào

~~~text
                         NGUỒN DỮ LIỆU
                              |
            +-----------------+------------------+
            |                 |                  |
       CSV / JSON /       SSTables từ        Sự kiện / CDC /
       Parquet / RDBMS    Cassandra          ứng dụng nguồn
            |                 |                  |
       Phải chuyển type   SSTable format       Chọn semantics
       & primary key      /schema/partitioner   của mutation
            |                 |                  |
       COPY / DSBulk /    sstableloader       Driver / Spark /
       Spark / Java       (streaming)         pipeline riêng
            |                 |                  |
            +-----------------+------------------+
                              |
                      CLUSTER CASSANDRA
             ring / RF / disk / compaction / CQL
                              |
                  ĐỐI CHIẾU DỮ LIỆU NGHIỆP VỤ
~~~

**Logical load** biến đầu vào thành mutation CQL mới. Nó chịu logic `INSERT/UPDATE/DELETE`, write timestamp/TTL đã khai báo và replication hiện tại. **Physical SSTable load** đưa dữ liệu đã được encode trong SSTable vào storage engine; timestamp, TTL và tombstone trong file vẫn có ý nghĩa và không tự trở thành một ghi CQL mới.

### 2.1. Mục tiêu bulk load khác restore

| Mục tiêu | Ví dụ | Điều cần quan tâm nhất |
|---|---|---|
| **Initial seed** | Nạp CSV 20 triệu giao dịch vào cluster mới | Schema, partition distribution, tốc độ và kiểm đủ khóa |
| **Historical backfill** | Nạp đơn hàng 2020–2024 vào bảng đang có traffic | Không ghi đè dữ liệu mới, TTL, cutoff, dual-write |
| **SSTable migration** | Chuyển backup từ ring 3 node sang ring 5 node | SSTable compatibility, topology/RF, streaming |
| **Schema redesign** | Từ bảng `orders_by_id` sang `orders_by_customer_day` | Biến đổi khóa, fan-out, consistency của nhiều bảng |
| **Incremental catch-up** | Nạp mutation xuất hiện sau snapshot | Thứ tự/version/idempotency, CDC retention |
| **Local node recovery** | Node mất đĩa, còn SSTable copy đúng ranges | Thường xem replace/rebuild/repair hoặc local import |

Bulk load từ CSV không phải một cách hoàn nguyên xóa nhầm có bảo đảm; `COPY FROM` thường phát sinh timestamps mới, nên có thể **vượt qua tombstone/newer update** nếu không thiết kế dữ liệu. Ngược lại, load SSTable cũ có thể không hiện dữ liệu vì bị tombstone mới hơn che.

## 3. Ma trận chọn công cụ

| Công cụ | Nhận dữ liệu | Cách ghi | Trường hợp phù hợp | Hạn chế chính |
|---|---|---|---|---|
| **`cqlsh COPY FROM`** | CSV (text) | CQL mutations qua cluster | Dữ liệu nhỏ/vừa, PoC, import có kiểm soát | Không phải ETL quy mô lớn; xử lý lỗi/type/TTL hạn chế |
| **`cqlsh COPY TO`** | Table CQL → CSV | Read/paging và serialize | Trích xuất dữ liệu nhỏ/vừa để kiểm/lab | Không là consistent snapshot cấp cluster, không bảo toàn SSTable metadata |
| **DataStax Bulk Loader (DSBulk)** | CSV/JSON và connectors theo bản | Song song hóa CQL mutations | Dataset lớn hơn COPY, mapping và logging tốt, điều tiết throughput | Vẫn là CQL writes; cần kiểm connector/version/auth/schema |
| **Spark Cassandra Connector** | Spark DataFrame: Parquet/JSON/JDBC/CSV… | Distributed reads/writes | ETL/transformation phức tạp, scale-out | Overhead Spark, shuffle, skew, version compatibility |
| **Java Driver 4.x importer** | Nguồn tùy ứng dụng | Prepared CQL writes bounded async | Pipeline nghiệp vụ, custom validation, idempotency/CDC | Tự chịu trách nhiệm concurrency/retry/checkpoint |
| **`sstableloader`** | Cassandra SSTable files | Streaming đến natural replicas | Migrate/seed từ SSTables, topology đích khác | Không đọc CSV; yêu cầu format/schema/partitioner tương thích |
| **`nodetool import`** | SSTables cục bộ | Nạp file vào **một node** | File restore cục bộ đúng token ranges | Không stream tự động tới tất cả replica; không thay loader |
| **SSTable writer + loader** | Input đã transform → SSTables offline | Tạo SSTables rồi stream | Pipeline chuyên dụng được kiểm chứng | Phức tạp format/versions; cần thư viện writer tương thích |

### 3.1. Cây quyết định nhanh

~~~text
Nguồn là SSTable hợp lệ từ Cassandra?
  |
  +-- CÓ --> Đích có ring/RF/node ownership khác?
  |            |
  |            +-- CÓ --> Ưu tiên sstableloader
  |            |
  |            +-- KHÔNG --> Muốn stream toàn cluster?
  |                         +-- CÓ: sstableloader
  |                         +-- KHÔNG, local file đúng node/range:
  |                                   cân nhắc nodetool import
  |
  +-- KHÔNG --> Là CSV đơn giản, số lượng vừa và cần thao tác nhanh?
               |
               +-- CÓ --> COPY FROM + dry-run/baseline/validation
               |
               +-- KHÔNG --> Có mapping và cần load lớn kiểu CLI?
                            +-- CÓ: DSBulk sau kiểm version
                            +-- KHÔNG: ETL phức tạp/phân tán?
                                       +-- CÓ: Spark Connector
                                       +-- KHÔNG: Java Driver pipeline
~~~

Các tiêu chí “vừa”/“lớn” **không có ngưỡng số dòng chung**. Một triệu row 200 bytes với partition keys phân bố đều khác một triệu row mỗi row chứa blob 1 MiB và tập trung vào một tenant. **Số partition, kích thước và skew** quan trọng hơn số row đơn lẻ.

### 3.2. Khi nào không nên dùng một công cụ?

- **`COPY FROM`**: dataset hàng trăm GiB/TiB với mapping nhiều bảng và cần resumability mạnh; cần cân nhắc DSBulk/Spark/custom ETL.
- **`sstableloader`**: đầu vào chỉ là CSV/JSON hoặc cần đổi primary key/phân tách row theo nghiệp vụ. Phải transform trước bằng công cụ khác.
- **`nodetool import`**: backup từ ring cũ có tokens không thuộc node đích, hoặc muốn stream tới toàn cluster.
- **Spark**: một file CSV vài KB hoặc môi trường không có Spark; chi phí vận hành vượt lợi ích.
- **Batch CQL khổng lồ**: không thay bulk loader; logged batch nhiều partition tạo overhead và áp lực coordinator.

## 4. Lập kế hoạch dung lượng trước khi nạp

### 4.1. Không chỉ đếm dòng

Lập bảng đầu vào:

| Thuộc tính | Ví dụ giả định | Ảnh hưởng |
|---|---:|---|
| Số row | 20 triệu | Tổng request/mutation |
| Kích thước trung bình một row | 1 KiB | Dung lượng dữ liệu logic |
| Số distinct partitions | 4 triệu | Phân tán token load |
| P99 partition size | 15 MiB | Hot/wide partitions, reads/compaction |
| Largest partition | 1 GiB | Rủi ro một node/replica bị nóng |
| RF | 3 | Dữ liệu được ghi tới nhiều natural replicas |
| Đích | 6 nodes, 1 DC | Disk/network capacity |
| TTL/DELETE/updates | 30% row có TTL | Tombstones và compaction |
| Cửa sổ import | 6 giờ ngoài peak | Mức throughput cần |

Nếu 20 triệu rows trong 6 giờ, throughput logic trung bình cần:

\[
\frac{20\,000\,000}{6 \times 3600} \approx 926\ \text{rows/s}.
\]

Đây là **mục tiêu ingest logic**, không phải số disk writes thật. Với RF=3, các replica cùng nhận mutation, nhưng overhead bytes/CPU/disk phụ thuộc topology, compression, memtable, compaction, indexes và retry; **không nhân bừa ba lần thành số IOPS chính xác**.

### 4.2. Dự phòng tài nguyên

- Disk: dữ liệu logic sau encode/compression × RF, cộng index/SAI, file tạm, compaction output và snapshot retention.
- CPU: serialization, validation, write path, compaction, compression, checksum.
- RAM: memtable, buffers, page cache, JVM heap/off-heap, client page/batch buffers.
- Network: client→coordinator, coordinator→replica, internode streaming và cross-DC.
- Availability: các replica cần giữ quorum/CL của ứng dụng đang đọc/ghi.
- Workload: nhập liệu có thể ảnh hưởng p99 của **các query families khác**, không chỉ batch process.

Không để disk gần đầy rồi bắt đầu streaming. SSTable compaction sau khi load có thể cần **temporary headroom** đáng kể, đặc biệt khi nhiều SSTables sinh cùng lúc.

### 4.3. Tư duy arrival rate và service rate

~~~text
Input rows/s
    |
    v
Importer concurrency & throttle
    |
    v
Coordinator / replica mutation stages
    |
    v
CommitLog + Memtable --> Flush --> SSTables --> Compaction
    |                    |                   |
 Client timeouts     PendingFlushes    PendingCompactions
    |                    |                   |
    +--------------------+-------------------+
                         |
                 Quan sát backpressure
~~~

Nếu input rate vượt khả năng bền vững của storage, queue có thể chỉ tăng **sau một thời gian dài**: ban đầu memtable/cache hấp thụ được burst, nhưng flush/compaction dần chiếm disk. Vì vậy đừng công bố throughput “tối đa” chỉ từ 30 giây đầu.

## 5. Schema là hợp đồng của toàn bộ quá trình nạp

### 5.1. Thiết kế theo truy vấn trước khi chọn loader

Ví dụ ứng dụng cần hai đường truy cập:

1. Xem 50 sự kiện gần nhất của một tenant trong một ngày.
2. Đọc một sự kiện cụ thể theo tenant/ngày và event ID.

Một bảng mẫu:

~~~sql
-- Lab một node; production nhiều DC dùng NetworkTopologyStrategy.
CREATE KEYSPACE IF NOT EXISTS bulk_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS bulk_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

- Partition key `(tenant_id, day)` giới hạn phạm vi dữ liệu của một tenant/ngày.
- Clustering columns `event_time, event_id` hỗ trợ đọc theo thời gian trong partition và tránh trùng row.
- `status` và `note` là regular columns. Không có index/access path mặc định cho tìm kiếm toàn cluster theo `status`.
- Với tenant rất lớn, một ngày có thể vẫn quá rộng: cần thêm **bucket nhỏ hơn hoặc shard có thể truy vấn được**, sau khi tính fan-out của ứng dụng.
- Nếu nghiệp vụ cần tra cứu trực tiếp bằng `event_id` mà không biết ngày, có thể cần **bảng theo truy vấn thứ hai**.

Không thể đổi partition key bằng `ALTER TABLE` trên bảng đã có dữ liệu để “chia đều lại”. Thường phải **CREATE TABLE mới**, nạp lại bằng key mapping đúng và đổi đường đọc/ghi có kế hoạch.

### 5.2. Kiểm CQL types và nguồn dữ liệu

| Kiểu Cassandra | Dữ liệu từ CSV/JSON | Rủi ro nếu mapping sai |
|---|---|---|
| `text` | UTF-8, có thể chứa dấu phẩy/newline/Unicode | CSV quoting, lỗi encoding, mất dấu |
| `uuid` | Dạng UUID chuẩn | Không dùng số thứ tự hay timestamp thay UUID |
| `timeuuid` | UUID phiên bản 1 mang thời gian | UUID v4 không hợp lệ; không tự sinh nếu cần bảo toàn ordering |
| `date` | `YYYY-MM-DD` | Nhầm timezone/cột timestamp |
| `timestamp` | ISO-8601 có timezone/UTC | Dịch giờ, mất precision khi nguồn dùng nano/microseconds |
| `decimal` | Số thập phân có độ chính xác | Dấu decimal, separator theo locale, mất trailing precision |
| `int`/`bigint` | Số nguyên trong range | Overflow, dấu phân tách hàng nghìn, null |
| `boolean` | true/false theo parser | `1/0` hoặc “yes/no” không chắc được chấp nhận |
| `blob` | Byte encoded theo CQL connector | CSV raw bytes không tự hợp lệ |
| `list`/`set`/`map`/UDT | Phải serialize theo cú pháp/connector được hỗ trợ | CSV string phẳng không tự là collection/UDT đúng |
| `counter` | Counter mutation riêng | Không thể coi như `INSERT` số nguyên bình thường |

**Điểm chống mất dữ liệu:** Không chỉ ép thành công type. Ví dụ nguồn có `2026-11-21T23:30:00+07:00` mà chuyển thành `2026-11-21T23:30:00Z` sẽ dịch thời điểm thực **7 giờ**. Nếu partition key dùng ngày địa phương, phải quy định rõ ngày được tính theo timezone nào; không trộn UTC day và local day vô ý.

### 5.3. Primary key rỗng và duplicate input

- Primary-key components không được null. Một dòng CSV thiếu `tenant_id` hoặc `day` phải vào **quarantine**, không gán vào bucket “unknown” nếu nghiệp vụ chưa cho phép.
- Hai dòng với **cùng primary key** là hai mutation vào **cùng row**, không phải hai dòng mới. Theo timestamp và column semantics, giá trị sau có thể che giá trị trước.
- Tạo `event_id` mới theo mỗi lần retry sẽ tạo **hàng trùng về nghiệp vụ**. Giữ event ID ổn định và idempotency key nếu nguồn có định danh.
- `INSERT` null vào regular column có thể sinh tombstone/delete semantics; khác với **không đưa cột vào mutation**. Đừng biến ô CSV trống thành xóa dữ liệu đang có mà không biết.

### 5.4. Replication và consistency trước khi nạp

Production nhiều datacenter nên có keyspace strategy/RF phù hợp:

~~~sql
-- DDL minh họa; chỉ chạy nếu dc1/dc2 THỰC SỰ tồn tại.
CREATE KEYSPACE production_events
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': '3',
    'dc2': '2'
};
~~~

`RF` là số bản sao theo DC, **không phải** số row hay một lựa chọn tăng tốc tự do. Với `LOCAL_QUORUM`, yêu cầu số replica phản hồi trong local DC tương ứng với RF; tăng throughput bằng cách hạ CL là thay **hợp đồng nhất quán**, không phải một tối ưu tương đương. Nếu RF mới đổi sau khi dữ liệu đã được nạp, cần có **repair/rebuild/streaming runbook** để dữ liệu lịch sử tới replica mới.

## 6. `cqlsh COPY FROM`: nạp CSV trực tiếp

### 6.1. Cú pháp nền tảng

~~~sql
-- Chạy trong cqlsh. File CSV nằm tại máy CHẠY cqlsh.
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) FROM '/srv/bulk-lab/events.csv'
WITH HEADER = TRUE
AND DELIMITER = ',';
~~~

`COPY FROM` đọc CSV, chuyển field sang CQL types theo schema rồi thực hiện các writes. **Nó không nhận SSTables**, không tự quyết định primary key mới và không biến cluster thành nguồn dữ liệu “tại một snapshot nhất quán”.

**File path là local của client `cqlsh`**, không phải đường dẫn phải tồn tại trên mọi Cassandra node. Nếu `cqlsh` chạy trong container, file phải được mount vào container đó. Nếu chạy từ laptop, đường dẫn máy chủ `/var/lib/...` không tự truy cập được.

### 6.2. CSV mẫu với quoting và Unicode

~~~csv
tenant_id,day,event_time,event_id,status,amount,note
tenant-a,2026-11-21,2026-11-21T08:00:00Z,11111111-1111-1111-1111-111111111111,NEW,1200.50,"Đơn mới, đã xác nhận"
tenant-a,2026-11-21,2026-11-21T08:05:00Z,22222222-2222-2222-2222-222222222222,PAID,1200.50,"Khách ghi: ""giao buổi sáng"""
tenant-b,2026-11-21,2026-11-21T09:10:00Z,33333333-3333-3333-3333-333333333333,NEW,75.25,"Đặt qua ứng dụng"
~~~

CSV này dùng dấu phẩy làm delimiter, **double quote** cho field chứa dấu phẩy, và hai dấu `""` để escape dấu quote bên trong. Các ký tự tiếng Việt cần encoding thống nhất, nên dùng UTF-8. Dòng có newline trong quoted field cần parser CSV đúng chuẩn; **không** tự split text bằng `line.split(",")`.

Vì các giá trị `event_id` khác nhau, ba dòng là ba primary keys riêng. Trường `note` chứa dấu phẩy không làm phát sinh cột thứ tám khi quoting được xử lý đúng.

### 6.3. Shared options và COPY FROM options quan trọng

Theo tài liệu Apache `cqlsh`, các tên options đáng chú ý:

| Option | Phạm vi | Ý nghĩa | Quy tắc |
|---|---|---|---|
| `HEADER` | FROM/TO | Dòng đầu chứa tên cột hay không | Đặt rõ `TRUE` khi file có header |
| `DELIMITER`, `QUOTE`, `ESCAPE` | FROM/TO | Cú pháp CSV | Khớp đúng nguồn, tránh lệch cột |
| `NULLVAL` | FROM/TO | Chuỗi đại diện null, mặc định là `null` | Khác với empty text; phải thiết kế mapping |
| `ENCODING` | FROM/TO | Encoding text | Chọn UTF-8 và kiểm file thật |
| `NUMPROCESSES` | FROM/TO | Số tiến trình xử lý của cqlsh COPY | Tăng có thể gây tải client/server; không mặc định tăng |
| `INGESTRATE` | FROM | Giới hạn số rows/giây xử lý | Chọn theo SLO/capacity |
| `MAXROWS`, `SKIPROWS`, `SKIPCOLS` | FROM | Giới hạn/skip vùng dữ liệu | Phù hợp lab/chunking; phải kiểm tránh mất dòng |
| `MAXBATCHSIZE`, `MINBATCHSIZE` | FROM | Kích thước batch trong importer | Không tăng vô hạn; tránh huge batches |
| `CHUNKSIZE` | FROM | Số row chuyển cho worker process | Tác động memory và overhead |
| `MAXATTEMPTS` | FROM/TO | Số lần thử chunk/range | Không đảm bảo idempotency nghiệp vụ |
| `MAXPARSEERRORS`, `MAXINSERTERRORS` | FROM | Ngưỡng lỗi được bỏ qua | Theo dõi file lỗi; không cho lỗi im lặng |
| `ERRFILE` | FROM | File chứa các dòng không nạp được | Bảo vệ dữ liệu nhạy cảm và replay có kiểm soát |
| `RATEFILE` | FROM/TO | Ghi thống kê tốc độ | Dùng để đo throughput nếu được phép |

Không có một cấu hình `NUMPROCESSES`/`INGESTRATE` chuẩn cho mọi cluster. Chọn từ **baseline** và khả năng của storage; kiểm `COPY ... HELP`/tài liệu đúng binary trước khi đặt option nâng cao. `COPY` có thể phân tích/thực thi theo chunks, nên nhiều lần retry không đồng nghĩa “exactly once”.

### 6.4. Mẫu load có giới hạn trong staging

~~~sql
-- Chỉ là cấu hình ví dụ cho cluster LAB.
-- Không dùng 300 rows/s như khuyến nghị production.
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) FROM '/srv/bulk-lab/events.csv'
WITH HEADER = TRUE
AND INGESTRATE = 300
AND MAXPARSEERRORS = 0
AND MAXINSERTERRORS = 0
AND ERRFILE = '/srv/bulk-lab/copy-import-errors.csv';
~~~

`MAXPARSEERRORS=0` và `MAXINSERTERRORS=0` trong ví dụ khiến việc gặp lỗi không được “bỏ qua” theo ngưỡng cấu hình; operator vẫn phải kiểm **exit status, summary, file lỗi và số rows thực tế**. Không suy rằng cqlsh đã đưa toàn bộ dữ liệu vào Cassandra chỉ vì không có exception hiển thị trên màn hình.

### 6.5. `cqlsh COPY TO`: xuất thử một bảng

~~~sql
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) TO '/srv/bulk-lab/events-export.csv'
WITH HEADER = TRUE
AND ENCODING = 'UTF8';
~~~

`COPY TO` thực hiện nhiều truy vấn đọc/paging theo token ranges và ghi CSV ở client. **Không phải physical SSTable backup**: không bảo toàn write timestamps, tombstones, TTL/expiration metadata, commit log và lịch sử cập nhật. Nếu writes tiếp tục trong lúc export, một CSV xuất dần theo range có thể chứa dữ liệu từ **nhiều thời điểm**, không phải atomic snapshot.

Không dùng `COPY TO` làm bằng chứng RPO=0 hay phương án restore đầy đủ cho bảng chứa DELETE/TTL cần được tái lập đúng. Khi chỉ xuất vài trăm rows cho bài học, công cụ vẫn rất hữu ích.

### 6.6. Lỗi CSV có thể làm “thành công về cú pháp, sai về nghiệp vụ”

| Lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Sai cột do quote | `"Hà Nội, Việt Nam"` bị tách đôi | Dùng CSV parser đúng, kiểm field count |
| Dấu thập phân theo locale | `1.200,50` | Chuẩn hóa decimal separator trước import |
| Null vs empty string | Text `null` bị hiểu là NULLVAL | Chọn marker được phép, validate nguồn |
| Lỗi Unicode/BOM | Tên cột đầu có BOM | Dùng UTF-8 sạch, kiểm header byte đầu |
| Sai timezone | `+07:00` bị coi là `Z` | Chuẩn hóa instant và day bucket |
| Duplicate primary key | Hai dòng `tenant-a/day/time/id` giống nhau | Kiểm duplicate và phiên bản nghiệp vụ |
| Bỏ trường bắt buộc | `event_id` rỗng | Quarantine, không tự sinh ID khi retry |
| CSV formula injection ở bản xuất | Cell bắt đầu `=` hoặc `+` | Không mở dữ liệu untrusted trực tiếp trong spreadsheet mà không escape/sanitize |

**Đường xử lý đúng:** parse → validate → quarantine rows lỗi → load một mẫu nhỏ → đối chiếu theo primary key → mở rộng. Không dùng `COPY FROM` để tự động “làm sạch” dữ liệu nguồn không rõ semantics.

## 7. DataStax Bulk Loader (DSBulk): CSV/JSON với mapping và observability tốt hơn

DSBulk là một công cụ bulk **dựa trên CQL/Java Driver**, đọc nguồn như CSV/JSON, áp dụng mapping rồi chạy các prepared writes hoặc reads theo cấu hình. Nó giúp vượt một số giới hạn vận hành của `cqlsh COPY` khi nhập lớn, nhưng **không đổi nguyên lý Cassandra**: partition key, RF/CL, timestamp/TTL, disk/compaction vẫn phải đúng.

### 7.1. Ví dụ nhập cùng file CSV

~~~bash
# Cần cài DSBulk tương thích và kết nối tới cluster LAB.
# -h là contact point(s), không phải storage streaming port.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab \
  -t events_by_tenant_day \
  -url /srv/bulk-lab/events.csv \
  -header true
~~~

Theo tài liệu DSBulk, nếu CSV có header cùng tên các cột CQL, loader có thể suy mapping; **khuyến nghị xác định mapping tường minh** khi production schema/CSV có nhiều cột hoặc tên khác nhau. Với file không có header, có thể map theo index:

~~~bash
# Chỉ ví dụ cho CSV không header, đã kiểm đúng thứ tự hai cột.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab \
  -t demo_two_columns \
  -url /srv/bulk-lab/no-header.csv \
  -header false \
  -m '0=tenant_id,1=event_id'
~~~

`demo_two_columns` là **tên bảng giả định** để minh họa mapping, không phải bảng đã tạo ở mục 5. Không chạy lệnh thứ hai nếu chưa tạo bảng/schema tương ứng.

### 7.2. Dry run và điều tiết concurrency

~~~bash
# Kiểm mapping/dữ liệu đầu vào mà không ghi vào bảng.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab -t events_by_tenant_day \
  -url /srv/bulk-lab/events.csv \
  --dryRun
~~~

Sau khi sample/dry run đúng, giới hạn số query in flight:

~~~bash
# 16 chỉ là giá trị khởi đầu minh họa trên LAB.
dsbulk load \
  -h 127.0.0.1 \
  -k bulk_lab -t events_by_tenant_day \
  -url /srv/bulk-lab/events.csv \
  --engine.maxConcurrentQueries 16
~~~

`--engine.maxConcurrentQueries` là **safeguard về concurrency**, không phải cam kết cố định rows/giây: throughput còn tùy latency, batch size và backpressure. Theo hướng dẫn DSBulk hiện hành, đây là option được ưu tiên hơn một số executor rate/in-flight options cũ. Không tăng từ 16 lên hàng nghìn chỉ vì nguồn CSV chưa đọc hết.

### 7.3. Error logs và quarantine

Một lần DSBulk load có thể tách lỗi thành:

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Connector/parser | Dòng CSV sai quoting hoặc JSON lỗi syntax | Quarantine file/dòng gốc, sửa encoding/parser |
| Mapping | CSV thiếu field primary key, type không chuyển được | Sửa schema mapping hoặc dữ liệu nguồn |
| Write/server | Timeout, unavailable, overload, auth failure | Chẩn đoán CL/node/resource, retry **có điều kiện** |
| LWT/Paxos | Conditional write không áp dụng | Đây có thể là **xung đột nghiệp vụ**, không retry vô hạn |

DSBulk có operation logs và các file `connector.bad`, `mapping.bad`, `load.bad`, `paxos.bad` tùy lỗi và cấu hình. Các file này có thể chứa **dữ liệu nguyên bản** từ nguồn, do đó phải mã hóa và hạn chế truy cập. Không phát công khai error files để tiện debug.

**Không lấy “rows processed” làm “rows đúng đã tồn tại trên cluster”.** Một dòng nguồn có thể cùng primary key với dòng khác, bị tombstone/TTL che hoặc ghi đè bởi mutation mới hơn; cần kiểm kết quả logic.

### 7.4. Chọn DSBulk thay vì COPY khi nào?

- Nguồn nhiều file CSV/JSON, cần kiểm mapping tường minh và log lỗi từng record.
- Cần chia ingestion theo batches/chunks, có summary/metrics và giới hạn concurrency.
- Dữ liệu đủ lớn khiến cqlsh COPY khó điều phối, nhưng pipeline không đòi Spark cluster.
- Có nhóm vận hành được DSBulk version, auth/TLS, config và giữ log an toàn.

**Không dùng DSBulk để né thiết kế partition key.** Nó có thể ghi nhanh vào một hot partition và làm một nhóm natural replicas quá tải; lỗi gốc nằm ở data model.

## 8. Spark Cassandra Connector: transform trước khi nạp phân tán

Với nguồn Parquet/Delta/JDBC/JSON lớn, phải làm sạch và biến đổi schema phức tạp, Spark có thể phù hợp hơn CSV copy đơn giản.

### 8.1. Pipeline tổng quát

~~~text
RDBMS/Parquet/JSON/CSV
          |
      Spark read
          |
    Validate schema
    Normalize timezone/IDs
    Deduplicate by business key
    Derive tenant/day buckets
          |
      Repartition/shuffle
          |
    Cassandra Connector
          |
    Prepared/mapped CQL writes
          |
       Cassandra
          |
    Sample + full reconciliation
~~~

Spark **không tự sửa** duplicate primary keys hay thứ tự CDC. Nếu input streaming được replay, cần cơ chế idempotency/version ở tầng dữ liệu. Chia quá nhiều Spark partitions/concurrent tasks có thể tạo write spike; chia quá ít lại gây bottleneck ở một executor.

### 8.2. Ví dụ Spark Scala mang tính minh họa

~~~scala
import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

val spark = SparkSession.builder()
  .appName("CassandraBulkLab")
  .getOrCreate()

val raw = spark.read
  .option("header", "true")
  .option("inferSchema", "false")
  .csv("/srv/bulk-lab/events.csv")

// Parse date/timestamp/UUID và amount theo schema mục tiêu.
// Trong workload thật phải kiểm lỗi null/format sau cast.
val normalized = raw.select(
  col("tenant_id"),
  to_date(col("day"), "yyyy-MM-dd").as("day"),
  to_timestamp(col("event_time")).as("event_time"),
  col("event_id"),
  col("status"),
  col("amount").cast("decimal(18,2)").as("amount"),
  col("note")
)

normalized.write
  .format("cassandra")
  .option("keyspace", "bulk_lab")
  .option("table", "events_by_tenant_day")
  .mode("append")
  .save()
~~~

Đây là **khung code** để giải thích flow, không bảo đảm biên dịch trong môi trường chưa cài connector tương thích. Với CQL type `uuid`, Spark connector có thể yêu cầu type native UUID thay vì String; cần dùng mapping/cast theo **connector version** hoặc đưa conversion vào một bước typed transformation. Cần cấu hình Spark Cassandra Connector dependency tương thích **Spark/Scala/Cassandra** và connection/auth/TLS.

Tài liệu connector hiện đại hỗ trợ `.format("cassandra")` cùng `keyspace`/`table`; ở một số codebase cũ, format class dài `org.apache.spark.sql.cassandra` vẫn xuất hiện. Không copy bất kỳ ví dụ cũ nào mà bỏ kiểm ma trận dependency.

### 8.3. Repartition có thể làm tốt hoặc hại

Spark job có thể repartition dữ liệu theo nhóm partition keys để tránh executor skew, nhưng cần cân bằng:

- Repartition toàn bộ theo `tenant_id` khi chỉ có vài tenant rất lớn có thể gom tải vào ít tasks.
- Repartition quá nhiều task khiến **driver/network/cluster** có hàng nghìn writes đồng thời.
- Hot partition của Cassandra vẫn hot dù Spark tasks được chia đều: tất cả mutation cùng key phải đi tới cùng natural replica set.
- Shuffle large datasets có thể tốn disk trên Spark workers và làm job chậm trước khi tới Cassandra.

Đo cả **source read, transformation, shuffle, Cassandra write**, không chỉ thời gian `save()`. Định nghĩa rõ duplicate resolution: nếu một event xuất hiện hai lần với versions khác nhau, `dropDuplicates` mù quáng có thể giữ bản sai.

### 8.4. Khi không dùng Spark

Một bảng vài ngàn rows hoặc một file CSV nhỏ không cần cluster Spark. Nếu workload cần đọc ghi event-by-event với custom transactional checks, một pipeline Java Driver có kiểm soát có thể đơn giản hơn. Spark phù hợp nhất khi **ETL/scale-out** là phần lớn công việc, không phải vì Cassandra “phải dùng Spark mới nhanh”.

## 9. `sstableloader`: bulk loading từ SSTable vào ring đang chạy

`sstableloader` đọc **SSTable files** từ một directory ổn định rồi stream dữ liệu đến natural replicas theo ring và replication strategy của cluster đích. Nó không đọc CSV, không thực thi mỗi hàng bằng một `INSERT` CQL thông thường và **không** tạo schema giúp bạn.

### 9.1. Từ snapshot thành tập SSTable staging

Ví dụ nguồn có snapshot:

~~~text
/var/lib/cassandra/data/source_events/
  events_by_tenant_day-<table_id>/
    snapshots/snap-20261121/
      nb-1-big-Data.db
      nb-1-big-Statistics.db
      nb-1-big-TOC.txt
      ... các components khác
~~~

Đường dẫn trên chỉ minh họa format. Mỗi SSTable có nhiều component cùng generation; prefix `nb`/`ma`, BIG/BTI và các file phụ tùy Cassandra version. Không copy chỉ `Data.db`.

Tạo **bản sao độc lập** vào staging, với cha là keyspace/table đích:

~~~text
/srv/loader-staging/bulk_lab/events_by_tenant_day/
    nb-1-big-Data.db
    nb-1-big-Statistics.db
    ...
~~~

Nếu tập từ nhiều source nodes có **trùng generation name**, không ghi đè cùng file trong một thư mục. Tách staging theo source-set hoặc dùng công cụ rename/rewrite có hỗ trợ; không đổi prefix một component rồi bỏ component khác.

### 9.2. Cú pháp và điều kiện

~~~bash
sstableloader --help

# Ví dụ loader chạy trên host có staging copy,
# contact points thuộc CLUSTER ĐÍCH, không phải nguồn.
sstableloader \
  --nodes 10.20.0.11,10.20.0.12 \
  --throttle-mib 16 \
  /srv/loader-staging/bulk_lab/events_by_tenant_day
~~~

| Tham số/điều kiện | Ý nghĩa |
|---|---|
| `--nodes` / `-d` | Initial target hosts để lấy topology; **không** là danh sách toàn bộ replica được ghi |
| Directory `<keyspace>/<table>` | Loader mặc định suy table đích từ parent path |
| `--target-keyspace` | Bản hỗ trợ có thể đổi target keyspace; không tự đổi tên table/schema |
| `--throttle-mib` | Giới hạn stream MiB/s, cần dựa capacity thực |
| Native/streaming ports, auth/TLS | Kết nối được 9042 chưa chứng minh internode streaming ports thông |
| SSTable format/partitioner/schema | Binary loader phải đọc được, và target phải tương thích |
| Source snapshot copy | Không dùng live SSTables đang bị compaction hoặc ghi đè |
| Disk/network headroom | Streaming có thể làm tăng compaction/IO trên target |

**Phân biệt nguồn và đích:** Tài liệu `sstableloader` có cảnh báo về chạy công cụ với SSTables đang được Cassandra quản lý trên local host. Cách an toàn là loader chạy trên **bản copy offline/staging**, trong khi **target cluster đang chạy** để nhận stream. Không dừng cluster đích chỉ vì công cụ đọc file từ host khác.

### 9.3. Vì sao loader phù hợp khi topology thay đổi?

~~~text
SOURCE (3 nodes, RF=3):       TARGET (5 nodes, RF=3):
    A -- B -- C                    P -- Q -- R -- S -- T
     \    |    /                     \      |       /
       snapshot                       new token ring
           |                                 ^
    copy SSTables                              |
           |                                 |
       sstableloader -------------------------+
            Stream sections by NEW token ownership
~~~

Không phải A→P, B→Q, C→R theo thứ tự. Token ranges và natural replicas có thể đã đổi. `sstableloader` đặt dữ liệu theo **replication của đích** thay vì giữ node placement của file nguồn.

### 9.4. Sstableloader không phải công cụ sửa dữ liệu nghiệp vụ

- Cùng primary key với timestamps khác nhau được hòa giải theo semantics Cassandra, không theo “file nạp sau thắng”.
- Tombstone có timestamp mới hơn vẫn có thể che row từ SSTable cũ.
- TTL đã hết không tự reset khi stream lại file.
- Nếu tombstone đã purge và file cũ trở lại, có nguy cơ **zombie data**; phải đối chiếu deletion events.
- Loader thành công không chắc mọi token ranges từ nguồn đã có: snapshot một node có thể chỉ chứa một phần dataset.
- Các bảng denormalized/secondary indexes/materialized views có schema và data flow riêng; phải kiểm sau load.

Vì vậy nếu nguồn là dữ liệu cần **transform primary key hoặc làm sạch**, hãy dùng DSBulk/Spark/Java để tạo mutation mới theo thiết kế; không cố biến `sstableloader` thành SQL ETL.

## 10. `nodetool import`, `refresh` và `sstableloader` khác nhau như thế nào?

| Thuộc tính | `sstableloader` | `nodetool import` | `nodetool refresh` |
|---|---|---|---|
| Nguồn | SSTables staging | SSTables staging local | SSTables được đặt trong live table directory |
| Phạm vi | **Cluster/replicas** theo target ring | **Một node** được gọi | **Một node** được gọi |
| Token ownership | Loader chia range cho natural replicas | Có thể kiểm token của local node | Operator chịu trách nhiệm đặt file đúng |
| Target keyspace/table | Từ directory/option tương ứng | Tham số lệnh KS/table | Table directory và tham số |
| Kiểm integrity/cache/repaired state | Streaming path | Các tùy chọn verify/token/cache | Ít bước bảo vệ hơn, legacy |
| Topology nguồn/đích khác | **Ưu tiên** | Dễ sai placement | Dễ sai placement |
| Dùng cho CSV | Không | Không | Không |

`nodetool import` được khuyến nghị hơn legacy `refresh` trong hướng dẫn bulk loading ở các phiên bản hiện đại. Mẫu:

~~~bash
# Chỉ thực hiện trên node được phép, file đúng schema và ranges.
nodetool help import
nodetool import -- bulk_lab events_by_tenant_day \
  /srv/local-staging/events_by_tenant_day
~~~

Nếu import báo token out of range, **đừng dùng `--no-tokens` để ép dữ liệu vào node**. Một node lưu file ngoài token ownership có thể gây tình trạng dữ liệu đọc không được hoặc replica lệch. Tương tự, tránh `--no-verify`/`--quick` khi chưa xác minh source.

**Khi node mới cần dữ liệu từ các replica còn khỏe**, đôi khi **replace/rebuild hoặc repair** phù hợp hơn local file import. Đây là bài nạp dữ liệu, không nên biến một sự cố node thành thao tác manual SSTable file copy khi chưa kiểm topology.

## 11. Timestamp, TTL, tombstone và idempotency khi nạp lại

### 11.1. Một “row” không có một timestamp duy nhất trong mọi trường hợp

Cassandra hòa giải dữ liệu ở mức cell/row/tombstone theo write timestamp (microseconds). Một hàng có thể có:

~~~text
PK = (tenant-a, day=2026-11-21, event_time=08:00, id=1111)
  status = PAID        writetime = 1_800_000_000_100_000
  amount = 1200.50     writetime = 1_800_000_000_090_000
  note   = "manual"    writetime = 1_800_000_000_110_000
~~~

Đây là các timestamp mô phỏng, không liên hệ trực tiếp với thời gian thật của dòng CSV. Khi `COPY TO` xuất một dòng CSV, các write timestamps này **không được xuất kèm mặc định**. `COPY FROM` tạo mutations mới và có thể ghi đè những cell mới hơn nếu dùng timestamp hiện tại.

### 11.2. Ví dụ backfill ghi đè dữ liệu live

~~~text
T0  Snapshot nguồn:
      order-123.status = NEW, source_version=1

T1  User cập nhật trên bảng ĐÍCH:
      order-123.status = PAID, source_version=2

T2  Backfill CSV cũ bằng COPY FROM:
      order-123.status = NEW
      (mutation có write timestamp của T2)

T3  Client đọc:
      có thể thấy NEW trở lại vì T2 mới hơn T1.
~~~

**Đây không phải lỗi của cqlsh**: loader thực thi write theo semantics Cassandra. Do đó đừng nạp CSV snapshot cũ trực tiếp vào bảng đang được ứng dụng ghi liên tục mà chưa có chiến lược bảo vệ version/order.

### 11.3. Các phương án bảo vệ thứ tự

| Phương án | Cách làm | Điều kiện/rủi ro |
|---|---|---|
| **Write pause có kiểm soát** | Tạm dừng writes trong cửa sổ ngắn, backfill, verify, mở writes | Phù hợp dataset nhỏ, RTO/downtime cho phép |
| **Bảng/keyspace mới cách ly** | Backfill vào bảng B, sau đó catch-up, cutover | Cần storage/dual-read/feature flag |
| **Source timestamps được giữ** | Ghi CQL với `USING TIMESTAMP` phản ánh thời điểm logic nguồn khi được phép | Cần metadata nguồn đáng tin, chính sách conflict thống nhất |
| **Business version + merge logic** | Chỉ chấp nhận phiên bản mới hơn qua pipeline/condition có kiểm soát | Không đơn giản dùng `INSERT` mù, LWT tốn chi phí |
| **CDC/outbox bắt kịp delta** | Chụp watermark T0, backfill snapshot, replay events sau T0 | CDC retention/order/completeness phải được bảo đảm |
| **Cutover theo tenant/bucket** | Khóa hoặc chuyển quyền ghi từng subset | Cần routing, ownership và rollback có kế hoạch |

Nếu nguồn có event version, **không dùng CQL client timestamp như một số thứ tự nghiệp vụ hoàn hảo**. Đồng hồ lệch giữa writer và write timestamp tương lai có thể làm cập nhật về sau bị che. Khi cần transaction logic, thiết kế conflict resolution dựa trên **idempotency key, source sequence, audit** và cơ chế điều phối phù hợp.

### 11.4. Giữ write timestamp khi thực sự có metadata

Đối với pipeline Java hoặc CQL được kiểm soát, CQL có thể chỉ định write timestamp:

~~~sql
-- Ví dụ concept; giá trị 1800000000100000 là microseconds,
-- phải được xác định từ nguồn đáng tin trước khi chạy.
INSERT INTO bulk_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, status)
VALUES (
    'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
    11111111-1111-1111-1111-111111111111, 'NEW'
) USING TIMESTAMP 1800000000100000;
~~~

`USING TIMESTAMP` chỉ điều khiển CQL mutation được tạo, **không tự phục hồi tombstone history** bị mất trong CSV export. Với source có nhiều timestamps **theo từng column**, một `INSERT` với một timestamp chung chưa bảo toàn toàn bộ lịch sử; phải lập kế hoạch chi tiết hoặc dùng SSTables/snapshot phù hợp.

### 11.5. TTL/expiration cần chính sách độc lập

~~~text
Nguồn T0: INSERT session USING TTL 3600
Sau T0 90 phút: nạp lại từ CSV

Nếu dùng COPY FROM không có TTL:
  session có thể tồn tại vô hạn trong target.

Nếu nạp lại với TTL 3600 như mới:
  session có thể sống thêm 1 giờ nữa.

Cả hai đều khác "session hết hạn đúng T0+3600".
~~~

Với dữ liệu có TTL, cần biết expiration gốc và chính sách:

1. Nếu bản ghi đã hết hạn theo thời gian hiện tại, **không tái tạo** trừ khi nghiệp vụ chủ ý.
2. Nếu còn sống, tính **remaining TTL** theo thời gian đích và xử lý sai số/race.
3. Nếu phải bảo toàn expiration/TTL chính xác, cân nhắc SSTable migration tương thích hoặc pipeline chuyên dụng có metadata đầy đủ.
4. Nếu có tombstone/DELETE hợp lệ sau T0, phải replay deletion và xác minh hàng **phải vắng**.

Không rút `gc_grace_seconds` để dọn data sau bulk load nếu chưa bảo đảm repair/retention: tombstone GC sớm có thể làm **zombie data** xuất hiện khi SSTables cũ được nạp lại.

### 11.6. Retry có phải idempotent?

CQL `INSERT` cùng primary key và cùng giá trị thường gần với thao tác upsert có thể replay, nhưng **không đủ để khẳng định exactly-once**:

- Retry với client timestamps khác nhau có thể tác động conflict resolution.
- Default TTL sẽ được tính mới khi mutation được gửi lại.
- `COUNTER UPDATE` tăng counter **không idempotent** theo cách INSERT point lookup.
- LWT `IF NOT EXISTS` có thể báo `[applied]=false` ở lần retry dù lần trước đã thành công.
- Một event dùng UUID mới mỗi retry có thể tạo nhiều rows.
- Ghi cùng dòng nhưng update những columns không đồng nhất có thể làm trạng thái trộn.

Chọn idempotency theo **nghiệp vụ và source event ID**, có checkpoint sau ACK/validation, và đối soát các trường hợp timeout “unknown outcome”. Không replay toàn bộ error file vô hạn.

## 12. Batching: vì sao `BEGIN BATCH` không phải bulk accelerator

Một hiểu lầm phổ biến là gom một triệu CQL inserts vào một `BEGIN BATCH` sẽ nhanh hơn. Trong Cassandra:

- **Logged batch nhiều partition** cần batchlog và coordination overhead; không phải transaction SQL/RDBMS toàn cục.
- **Unlogged batch** không loại bỏ I/O của mọi mutation, không bảo đảm atomic across partitions.
- Quá nhiều statement trong batch có thể gây warning và overload coordinator.
- Grouping vài mutations **trong cùng partition** đôi khi hợp lý, nhưng phải đo actual p99/throughput và semantics.
- DSBulk/cqlsh COPY có chính sách batch riêng; không tăng `MAXBATCHSIZE` vô hạn để tối ưu.

~~~sql
-- Không dùng mẫu này làm bulk loader production!
BEGIN BATCH
  INSERT INTO bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status
  ) VALUES (
    'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
    11111111-1111-1111-1111-111111111111, 'NEW'
  );
  INSERT INTO bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status
  ) VALUES (
    'tenant-b', '2026-11-21', '2026-11-21T08:00:00Z',
    22222222-2222-2222-2222-222222222222, 'NEW'
  );
APPLY BATCH;
~~~

Hai dòng thuộc **hai partitions khác nhau**; với một bulk importer, gửi prepared statements độc lập có giới hạn concurrency thường dễ kiểm soát hơn. Batch không phải cách vượt tắc nghẽn disk/compaction.

### 12.1. Đánh đổi song song và ổn định

Giả sử importer có `N` requests in flight và mean latency `W` giây; throughput hoàn thành tối đa theo trực giác khoảng `N/W` nếu công việc ổn định, không có retry hoặc bottleneck mới. Đây **không phải cam kết**: Cassandra có RF, coordinator, disk flush/compaction và partition skew.

Ví dụ 32 in-flight × 50 ms mean ≈ 640 requests/s là một phép tính lý thuyết. Khi tăng lên 256 in-flight mà disk await tăng gấp nhiều lần, throughput có thể không tăng nhưng tail latency/timeout tăng mạnh. Vì vậy cần **concurrency feedback** theo p99/error/resource, không cấu hình từ phép chia một lần.

## 13. Pipeline di chuyển schema khi ứng dụng vẫn hoạt động

Một dự án điển hình: bảng cũ `events_by_tenant` có partition quá rộng, cần chuyển sang `events_by_tenant_day` có time bucket.

### 13.1. Dữ liệu cũ và bảng mới không thể đổi khóa tại chỗ

~~~text
V1 (cũ):
  PRIMARY KEY ((tenant_id), event_time, event_id)
  => Tenant lớn có partition rất rộng

V2 (mới):
  PRIMARY KEY ((tenant_id, day), event_time, event_id)
  => Partition theo tenant/day

Không phải ALTER TABLE sửa partition key.
Phải CREATE TABLE V2, backfill, bắt kịp updates
và chuyển ứng dụng đọc/ghi.
~~~

### 13.2. Các pha an toàn

~~~text
                         NGUỒN V1 (live)
                               |
                Chọn watermark / snapshot T0
                               |
                    Backfill lịch sử T<=T0
                               |
                         BẢNG ĐÍCH V2
                               |
          +--------------------+--------------------+
          |                                         |
   CDC/outbox/delta từ T0                      Dual-write mới
          |                                         |
          +--------------------+--------------------+
                               |
                  Catch-up đến lag chấp nhận
                               |
                   Audit khóa/phiên bản/TTL
                               |
                    Canary reads từ V2
                               |
                     Cắt traffic từng nhóm
                               |
                   Theo dõi + rollback window
~~~

**Không có tính nguyên tử tự động giữa hai bảng** vì Cassandra không cung cấp cross-table transactions kiểu RDBMS cho mọi thao tác. Khi ứng dụng dual-write, một write V1 thành công và V2 thất bại cần cơ chế bù/sửa có thể lặp, chẳng hạn outbox hoặc event stream có durable retry và reconciliation.

### 13.3. Watermark và catch-up không được giả định theo wall clock đơn giản

Watermark có thể là offset/event sequence từ nguồn có **thứ tự đáng tin**. Chỉ ghi “T0=10:00 UTC” rồi quét V1 bằng CQL và đọc CDC sau 10:00 có thể bỏ sót mutation đến trễ, retry hoặc clock skew.

Một cách làm:

1. Chọn **source of truth** (event log/CDC/transactional snapshot) và checkpoint được bảo đảm.
2. Ghi watermark/offset của nguồn; định nghĩa tác động của event có timestamp trễ.
3. Nạp backfill từ snapshot nhất quán trong phạm vi hỗ trợ.
4. Catch-up các events sau checkpoint, replay idempotent theo version.
5. Đo lag/coverage tới mức chấp nhận, chứ không chỉ “source queue rỗng”.
6. Duy trì đối soát cho dữ liệu sau khi chuyển writes.

Nếu chỉ có snapshot Cassandra **không nguyên tử toàn cluster** mà không có change log tin cậy, phải **nêu giới hạn tính nhất quán của migration** và có thời gian quiesce/dual-write thích hợp. Không hứa zero-downtime/lossless từ một chuỗi `COPY TO`.

### 13.4. Cutover và rollback có điều kiện

| Pha | Điều kiện chuyển tiếp | Nếu không đạt |
|---|---|---|
| New schema deployed | DDL đúng, schema agreement và RF/DC phù hợp | Dừng, sửa schema trước |
| Backfill completed | Full source file coverage, mọi lỗi được triage | Chạy bù chỉ những chunks thiếu |
| Delta caught up | Lag thấp, version/order đúng, no unprocessed critical events | Chưa chuyển reads |
| Canary reads | Cùng kết quả/ordering/paging, p99 và error đạt | Rollback read flag, sửa V2 |
| Writes to V2 | Dual-write/outbox healthy và no data gap | Giữ V1 làm source, replay events |
| Full cutover | RPO/RTO, monitoring và rollback được duyệt | Giữ rollback window |
| Retire V1 | Không còn consumers, retention/backup đúng | **Không** DROP/TRUNCATE sớm |

**Rollback read routing** thường dễ hơn rollback **dữ liệu đã ghi một chiều**. Nếu sau khi cutover chỉ V2 nhận writes, muốn quay lại V1 phải có **reverse replication/replay** hoặc giữ V1 đồng bộ trong rollback window. Không cam kết “chỉ đổi feature flag trở lại V1” khi V1 đã bỏ lỡ dữ liệu mới.

## 14. Thực thi có kiểm soát: baseline, throttle, checkpoint và stop conditions

### 14.1. Baseline trước khi import

Mọi kế hoạch load production cần có:

| Nhóm | Giá trị cần ghi | Ý nghĩa |
|---|---|---|
| Cluster/ring | `nodetool status`, RF/DC, node down/joining, disk free | Biết đích có đủ replica/capacity |
| Application | QPS, query family, read/write p95/p99, timeout/unavailable | Đo tác động tới người dùng |
| Importer | Input rows/bytes, parsing errors, accepted/failed, retries | Tách tốc độ nạp với tính đúng |
| JVM/driver | In-flight, pool connections, client timeouts, retries | Phát hiện overload phía client |
| Storage write path | Memtable bytes, `PendingFlushes`, `CommitLog` waits | Phát hiện flush/commit-log chậm |
| Compaction | `PendingCompactions`, `Compaction.PendingTasks`, bytes compacted | Nhìn backlog đến sau burst |
| Read amplification | SSTables-per-read, tombstones/read | Tránh load làm đọc chậm hơn |
| OS | CPU, GC, disk await/IOPS, network, disk free | Tài nguyên vật lý còn dư |

Các lệnh read-only:

~~~bash
nodetool version
nodetool status
nodetool describecluster
nodetool tablestats bulk_lab.events_by_tenant_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool gcstats
~~~

`nodetool status` cho thấy ring/liveness, **không chứng minh dữ liệu đã nạp đủ**. `PendingCompactions` là ước lượng backlog, không phải số giây còn lại. Kết hợp lệnh với JMX/Prometheus và metrics ứng dụng **trong cùng cửa sổ UTC**.

### 14.2. Ramp-up thay vì bắt đầu tối đa

~~~text
PRE-FLIGHT:  đủ replica, disk, schema, source integrity
       |
  CANARY:   1 file / 1 token group / 1 tenant bucket
       |
  VERIFY:   parse + CQL results + p99 + resource
       |
  RAMP 1:   tăng import concurrency/INGESTRATE vừa phải
       |
  VERIFY:   pending flush/compaction có thoát backlog?
       |
  RAMP 2:   chỉ khi metrics và SLA đạt
       |
  FINAL:    checkpoint, catch-up, reconciliation
       |
  CUTOVER:  read/write flag có kế hoạch rollback
~~~

Mục tiêu là **maximum sustainable throughput**, không phải **peak 5-second throughput**. Nếu disk/compaction backlog tích lũy nhiều giờ, 10 phút canary có thể chưa đủ. Tăng concurrency từng bước và giữ một pha đủ dài để thấy hậu quả downstream.

### 14.3. Bảng điều kiện GO/HOLD/STOP

| Điều kiện | Phân loại | Hành động |
|---|---|---|
| Input checksum/header/schema chưa đúng | `STOP` | Sửa nguồn; không cho mutation sai đi vào target |
| Có row invalid hoặc PK null | `HOLD` hoặc `STOP` | Quarantine và quyết định có thể bỏ hợp lệ không |
| Node thiếu replica dẫn tới CL không đạt | `STOP` | Khôi phục availability trước |
| Write p99 tăng đáng kể, timeouts vượt SLO | `STOP/THROTTLE` | Giảm tốc, không làm mất yêu cầu consistency |
| Disk free xuống dưới headroom vận hành | `STOP` | Không tiếp tục streaming/compaction tự phát |
| `PendingFlushes` và blocked allocation kéo dài | `HOLD` | Điều tra disk/flush, điều tiết load |
| `PendingCompactions` tăng nhưng vẫn thoát sau peak, SLO ổn | `GO` có kiểm soát | Tiếp tục theo dõi |
| Thiếu dữ liệu trong một token range | `HOLD` | Kiểm source coverage/checkpoint và repair |
| DELETE/TTL đã purge xuất hiện trở lại | `STOP` | Audit và phục hồi logic, không chuyển traffic |
| Canary đủ mẫu, dữ liệu đúng, SLO và headroom đạt | `GO` | Mở rộng từng batch |

**Không đặt một ngưỡng cố định kiểu “pending > 20 là stop” cho mọi cluster.** Chọn threshold từ baseline, disk class, RF, compaction strategy và ứng dụng; với mất quorum hoặc dữ liệu sai nghiêm trọng, stop ngay không đợi ba cửa sổ.

### 14.4. Chunk manifest và checkpoint an toàn

~~~text
RUN_ID: orders-v2-backfill-2026w47
SOURCE_SNAPSHOT: snapshot-id-abc
DEST_SCHEMA_HASH: ddl-sha256-...
DEST_CLUSTER: cluster-v2/dc1

CHUNK_0001:
  source_file: events-0001.csv
  source_sha256: ...
  input_rows: 100000
  expected_unique_primary_keys: 99998
  tool: dsbulk load
  started_utc: ...
  finished_utc: ...
  parsed: 100000
  confirmed_written: ...
  failed_or_unknown_outcome: ...
  reconciliation: PASS/FAIL
  state: VERIFIED

CHUNK_0002:
  state: PENDING
~~~

Checkpoint `VERIFIED` chỉ nên được tạo sau khi **đã kiểm write outcomes và data validation**, không chỉ khi tool process thoát với exit code 0. Một failed write có thể đã được replica áp dụng trước khi client timeout; khi replay, giữ **cùng PK và semantics idempotent**.

### 14.5. Tách “parse error” và “unknown write outcome”

| Loại lỗi | Được phép retry ngay? | Lý do |
|---|---|---|
| CSV sai số cột | Không | Sửa đầu vào, retry không đổi kết quả |
| Primary key null | Không | Không có identity đúng |
| Type conversion lỗi | Không | Cần normalize/mapping |
| Authentication/TLS sai | Không | Sửa môi trường trước |
| Cassandra unavailable | Có thể sau khi khôi phục CL/health | Không phát thêm tải khi cluster đang bệnh |
| Client write timeout | **Chỉ theo idempotency policy** | Write có thể đã được áp dụng |
| LWT `[applied]=false` | Không coi là transport error | Có thể là conflict hợp lệ hoặc retry của thành công cũ |
| Source event duplicate | Theo dedup/version rule | Không tự biến thành dữ liệu mới |

`COPY`/DSBulk log lỗi nên có **source filename/line number hoặc event ID** đủ để đối chiếu; không ghi full nội dung PII vào dashboard thông thường. Bản error file được lưu theo chính sách bảo mật và retention.

## 15. Kiểm tính đúng: “nạp xong” khác “dữ liệu đúng”

### 15.1. Ba lớp validation

| Lớp | Câu hỏi | Bằng chứng |
|---|---|---|
| **Transport** | File/chunk đã được parse hoặc streamed hết chưa? | Exit code, bytes/rows, error/retry logs |
| **Replica placement** | Data có tới natural replicas/ranges/DC theo RF đích không? | Token coverage, ring, loader logs, repair checks |
| **Business correctness** | Mọi PK/columns, status/version, TTL/DELETE và bảng derived có đúng không? | Audit, expected key set, hashes/canonical serialization |

**Một `SELECT` thành công ở CL=`ONE`** không chứng minh mọi replica đã chứa data. Ngược lại, `LOCAL_QUORUM` thành công trong dc1 không xác nhận dc2 đã được nạp đủ. Trong migration lớn, xác minh theo **từng DC** phù hợp với mục tiêu phục vụ ứng dụng.

### 15.2. Không dùng `COUNT(*)` toàn cluster như phép kiểm duy nhất

`SELECT COUNT(*) FROM large_table` có thể quét phạm vi rất lớn, gây timeout và cạnh tranh read I/O. Kể cả nó trả đúng số hàng, ta vẫn có thể có:

- Một khóa bị thiếu nhưng một khóa trùng/cũ được nạp thay.
- Một `status` sai dù row count đúng.
- Dữ liệu hợp lệ bị tombstone/TTL che trong một DC nhưng không ở DC khác.
- Giá trị decimal/timezone/UUID sai mapping.
- Bảng denormalized bị lệch mà bảng base đếm vẫn đúng.

**Lab vài row có thể dùng count**, nhưng production nên dựa vào **source manifest + per-partition/token-range checksums hoặc sample/aggregate có kiểm soát**, kết hợp audit nghiệp vụ và đối soát toàn bộ khi được yêu cầu.

### 15.3. Tập khóa kiểm thử phải gồm hàng phải có và hàng phải vắng

~~~text
EXPECTED:
  tenant-a/day21/event-1111 -> status NEW, amount 1200.50
  tenant-a/day21/event-2222 -> status PAID, amount 1200.50
  tenant-b/day21/event-3333 -> status NEW, amount 75.25
  tenant-c/day21/event-4444 -> DELETED by audit at T1
  session-xxx                 -> EXPIRED by TTL at T2
~~~

Nếu chỉ kiểm ba hàng đầu, việc import SSTables cũ có thể **làm sống lại dữ liệu đã xóa** mà báo cáo vẫn cho PASS. Với dữ liệu nhạy cảm hoặc retention có ràng buộc pháp lý, kiểm “**must be absent**” là cổng riêng không thể bỏ.

### 15.4. Checksum logic cần serialization chuẩn

Nếu muốn hash dữ liệu nguồn/đích:

1. Chọn các cột được phép so, bao gồm primary key và business version.
2. Chuẩn hóa timestamp thành UTC instant, decimal thành định dạng canonical, collection order nếu kiểu không có thứ tự.
3. Định nghĩa NULL vs absent column, TTL còn hiệu lực và semantics của deleted rows.
4. Sắp xếp theo primary key hoặc dùng thuật toán multiset có thể kết hợp an toàn.
5. Tính checksum theo **bucket/token range** để tìm đúng phần lỗi, không chỉ một checksum toàn bảng.
6. Ghi version của serialization logic; đổi hàm chuẩn hóa có thể làm hash khác dù dữ liệu không đổi.

Hash trùng chỉ cho độ tin cậy theo **thuật toán/coverage** đã chọn. Không thể thay thế audit về các mutation đã DELETE hay các event bị mất trước khi snapshot.

### 15.5. Performance acceptance cũng là một cổng

Một migration có tất cả rows đúng nhưng làm `p99 read` tăng 10 lần và disk full trên một rack chưa đủ để chuyển traffic. Đặt cổng:

- Correctness: PK, columns, deletes/TTL, derived tables, CDC catch-up.
- Availability: ring/replicas/CL, timeouts, unavailables.
- Resource: CPU/disk/GC, pending flush/compaction, network và headroom.
- Application: query families, p95/p99, paging, connection pools và errors.
- Operability: checkpoint/rollback window, log integrity, on-call.

Chỉ công bố `MIGRATION_VALIDATED` cùng **phạm vi coverage** (sample/full) và mốc UTC, không tuyên bố “đầy đủ 100%” khi chỉ kiểm ba rows.

## 16. Lab A — Tạo CSV, nạp bằng cqlsh COPY và đối chiếu

**Mục tiêu:** Học quy trình nhỏ nhưng đầy đủ: schema → CSV chuẩn → `COPY FROM` → đọc đúng PK → `COPY TO` → giải thích tại sao export không là physical backup.

**Môi trường:** Cassandra 4.1/5.0 **lab một node**, `cqlsh` được phép đọc file trên host/container nơi chạy, và quyền tạo keyspace/table. Không thực hiện trên một bảng production đang có writes. Dữ liệu trong lab hoàn toàn giả lập.

### Bước 1 — Tạo schema lab

Chạy đoạn `CREATE KEYSPACE`/`CREATE TABLE` ở mục 5.1, sau đó kiểm:

~~~sql
DESCRIBE KEYSPACE bulk_lab;
DESCRIBE TABLE bulk_lab.events_by_tenant_day;

CONSISTENCY ONE;
~~~

Chỉ dùng `SimpleStrategy`/RF=1 trong **môi trường một node**. Production phải xác định RF/DC và CL theo hợp đồng nghiệp vụ.

### Bước 2 — Tạo CSV UTF-8 ở máy chạy cqlsh

Trên Linux lab, ví dụ:

~~~bash
mkdir -p /srv/bulk-lab

cat > /srv/bulk-lab/events.csv <<'CSV'
tenant_id,day,event_time,event_id,status,amount,note
tenant-a,2026-11-21,2026-11-21T08:00:00Z,11111111-1111-1111-1111-111111111111,NEW,1200.50,"Đơn mới, đã xác nhận"
tenant-a,2026-11-21,2026-11-21T08:05:00Z,22222222-2222-2222-2222-222222222222,PAID,1200.50,"Khách ghi: ""giao buổi sáng"""
tenant-b,2026-11-21,2026-11-21T09:10:00Z,33333333-3333-3333-3333-333333333333,NEW,75.25,"Đặt qua ứng dụng"
CSV

wc -l /srv/bulk-lab/events.csv
sha256sum /srv/bulk-lab/events.csv
~~~

`wc -l` dự kiến là 4 (1 header + 3 records) vì ví dụ không có newline trong quoted fields. Với CSV có multiline fields, **số dòng vật lý không bằng số records**; dùng parser chuẩn thay vì coi `wc -l` là thước đo tuyệt đối.

### Bước 3 — Nạp dữ liệu có giới hạn

Trong cqlsh:

~~~sql
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) FROM '/srv/bulk-lab/events.csv'
WITH HEADER = TRUE
AND INGESTRATE = 100
AND MAXPARSEERRORS = 0
AND MAXINSERTERRORS = 0
AND ERRFILE = '/srv/bulk-lab/copy-errors.csv';
~~~

Nếu cqlsh báo file không tồn tại, kiểm **host/container của client**, không chạy `chmod 777` trên data directory Cassandra để sửa. Nếu parser lỗi Unicode, kiểm file thật là UTF-8 và có BOM/locale không. Nếu tool vẫn báo lỗi, **không tiếp tục** bằng cách tăng ngưỡng lỗi thành unlimited.

### Bước 4 — Đọc và kiểm đúng primary keys

~~~sql
SELECT event_time, event_id, status, amount, note
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, status, amount, note
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-b'
  AND day = '2026-11-21';
~~~

Kỳ vọng:

| Partition | Clustering key | Status | Amount | Nội dung cần kiểm |
|---|---|---|---:|---|
| `tenant-a/2026-11-21` | 08:00, UUID `1111…` | NEW | 1200.50 | Chuỗi có dấu phẩy |
| `tenant-a/2026-11-21` | 08:05, UUID `2222…` | PAID | 1200.50 | Dấu quote kép được giữ đúng |
| `tenant-b/2026-11-21` | 09:10, UUID `3333…` | NEW | 75.25 | Unicode không lỗi |

Vì clustering order là `event_time DESC`, thứ tự trả về trong partition tenant-a thường là 08:05 rồi 08:00 khi query không thay ordering. Không tự so sánh thứ tự text CSV đầu vào với thứ tự CQL query để báo dữ liệu “đảo hàng”.

### Bước 5 — Xuất lại bằng COPY TO

~~~sql
COPY bulk_lab.events_by_tenant_day (
    tenant_id, day, event_time, event_id, status, amount, note
) TO '/srv/bulk-lab/exported.csv'
WITH HEADER = TRUE;
~~~

Đọc file xuất bằng CSV parser; kiểm **canonical values và primary keys**, không đòi byte-for-byte giống file đầu vào vì CQL có thể chuẩn hóa timestamp/decimal/ordering/quoting. `COPY TO` không xuất TTL/tombstone/write timestamps, không thay snapshot/backup đầy đủ.

### Bước 6 — Thử lỗi được kiểm soát

Tạo **file khác** với một dòng lỗi (không sửa bản nguồn đúng):

~~~csv
tenant_id,day,event_time,event_id,status,amount,note
tenant-z,2026-11-21,2026-11-21T11:00:00Z,not-a-uuid,NEW,99.99,"invalid key"
~~~

Ghi nó thành `/srv/bulk-lab/invalid.csv` rồi chạy `COPY FROM` tương tự với `MAXPARSEERRORS=0`. Kỳ vọng importer báo parse/type error và **không tạo row có UUID sai**. Thu output/error file để giải thích loại lỗi; không biến test này thành cách tạo hàng lỗi thực.

### Bước 7 — Chọn có dùng lại cùng file không?

Nạp lại cùng CSV có thể thực thi những `INSERT` mới theo cùng PK. Với lab bảng tách biệt không có mutations mới, có thể thấy vẫn ba rows; nhưng điều đó **không chứng minh mọi replay production đều an toàn**. Nếu một giá trị đã bị sửa/DELETE hoặc có TTL sau lần import đầu, reimport có thể tạo timestamp mới và thay kết quả. **Luôn có checkpoint/idempotency policy**.

## 17. Lab B — Stream SSTable bằng sstableloader sang keyspace riêng

**Mục tiêu:** Thấy sự khác nhau giữa CSV mutation load và SSTable streaming, đồng thời tránh ghi đè bảng đã tạo bằng COPY. Cần thêm disk và quyền `nodetool snapshot`, có thể bỏ qua lab này nếu môi trường không cho phép chạy loader.

### Bước 1 — Chốt trạng thái nguồn tại T0

Sau khi Lab A nạp đúng, trong cqlsh:

~~~sql
SELECT event_time, event_id, status, amount
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

Ghi state T0 cho ba keys.

### Bước 2 — Snapshot chỉ bảng lab

~~~bash
# Chạy nodetool trên node lab; kiểm help phiên bản.
nodetool help snapshot
nodetool snapshot \
  --tag bulk_lab_snapshot_01 \
  --table events_by_tenant_day \
  bulk_lab

nodetool listsnapshots
~~~

Không dùng `--skip-flush` trong bài này vì cần đưa các writes vừa thực hiện vào SSTables được snapshot. Snapshot là hard links tới SSTables trên node; để có backup độc lập cần **copy** ra vùng staging riêng.

### Bước 3 — Tạo target schema tương đương ở keyspace khác

~~~sql
CREATE KEYSPACE IF NOT EXISTS bulk_lab_streamed
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS bulk_lab_streamed.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    status text,
    amount decimal,
    note text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Nếu target đã có dữ liệu từ lần lab cũ, không thể dùng lại như một bảng rỗng rồi tuyên bố đang kiểm T0.** Tạo keyspace/table thử nghiệm mới có tên duy nhất trong môi trường của mình hoặc đối chiếu state tồn tại trước.

### Bước 4 — Ghi một mutation ở nguồn sau snapshot

~~~sql
UPDATE bulk_lab.events_by_tenant_day
SET status = 'UPDATED_AFTER_SNAPSHOT'
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21'
  AND event_time = '2026-11-21T08:00:00Z'
  AND event_id = 11111111-1111-1111-1111-111111111111;
~~~

Lúc này current source có `UPDATED_AFTER_SNAPSHOT`, nhưng snapshot T0 giữ giá trị `NEW`. Mục đích là chứng minh **sstableloader chuyển snapshot cũ chứ không replicate live writes sau T0**.

### Bước 5 — Chép SSTables vào staging target path

Ví dụ đường dẫn nguồn (không copy literal `<table-id>`):

~~~text
/var/lib/cassandra/data/bulk_lab/
  events_by_tenant_day-<table-id>/
    snapshots/bulk_lab_snapshot_01/
      nb-...-Data.db
      nb-...-Statistics.db
      ... SSTable components
~~~

Tìm thư mục thật:

~~~bash
find /var/lib/cassandra/data/bulk_lab \
  -type d -path '*/snapshots/bulk_lab_snapshot_01' -print
~~~

Sau khi điền `SNAP_DIR` bằng đường dẫn thật, tạo copy:

~~~bash
# Chỉ trên host LAB có quyền đọc snapshot.
SNAP_DIR="/var/lib/cassandra/data/bulk_lab/events_by_tenant_day-<table-id>/snapshots/bulk_lab_snapshot_01"
STAGING="/srv/loader-staging/bulk_lab_streamed/events_by_tenant_day"

mkdir -p "$STAGING"
chmod 700 "$STAGING"

# STAGING phải đang trống; nếu không trống, DỪNG để kiểm.
cp -a "$SNAP_DIR"/. "$STAGING"/
find "$STAGING" -maxdepth 1 -type f -print
~~~

Nếu table được trải trên nhiều data directories, phải thu SSTables từ **tất cả directories liên quan**. Nếu gom SSTables của nhiều node mà tên generation trùng, giữ staging tách riêng theo source sets để tránh overwrite.

### Bước 6 — Stream đến cluster lab đang chạy

~~~bash
sstableloader --help

# 127.0.0.1 chỉ đúng nếu loader chạy cùng host Cassandra lab.
sstableloader \
  --nodes 127.0.0.1 \
  --throttle-mib 8 \
  /srv/loader-staging/bulk_lab_streamed/events_by_tenant_day
~~~

Nếu native CQL port thông nhưng stream fail, kiểm internode storage port/TLS và logs. Nếu format/version không tương thích, **không** sửa SSTable bytes bằng tay; dùng binary phù hợp hoặc runbook chuyển format trên bản copy offline. Không để loader đọc SSTables live đang bị compaction đổi.

### Bước 7 — Kiểm snapshot T0 khác live source T1

~~~sql
CONSISTENCY ONE;

SELECT event_id, status
FROM bulk_lab_streamed.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_id, status
FROM bulk_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

Kỳ vọng ở target `bulk_lab_streamed`: event `1111…` vẫn là `NEW` từ T0. Ở source: event đó đã `UPDATED_AFTER_SNAPSHOT`. Đây là khác biệt cố ý để hiểu **SSTable snapshot vs live CQL mutation**.

Nếu target thiếu rows, kiểm loader output, source snapshot coverage, table path/schema, partitioner/format và TTL/tombstone; không chạy lại vô hạn mà chưa biết nguyên nhân.

### Bước 8 — Quan sát hiệu ứng trên cluster

~~~bash
nodetool status
nodetool netstats
nodetool tablestats bulk_lab_streamed.events_by_tenant_day
nodetool compactionstats
~~~

Sau khi load, SSTables có thể được compact và disk I/O tăng. Với ba rows, lab quá nhỏ để benchmark throughput của loader. Đạt lab khi **CQL target đúng T0** và người học giải thích được vì sao T1 chỉ hiện ở source.

## 18. So sánh kết quả của hai lab

| Điều kiện | Lab A: `COPY FROM` | Lab B: `sstableloader` |
|---|---|---|
| Input | CSV ở client | Bộ SSTable components từ snapshot |
| Target | `bulk_lab.events_by_tenant_day` | `bulk_lab_streamed.events_by_tenant_day` |
| Ghi data | CQL mutation mới | SSTable streaming |
| Write timestamps | Do CQL write/import semantics quyết định | Giữ timestamps có trong SSTable |
| TTL/tombstone history | CSV không tự mang đủ metadata | SSTable chứa metadata tương ứng |
| Target topology | CQL coordinator/replicas theo RF/CL | Loader stream tới natural replicas theo ring đích |
| Transform partition key | Có thể qua bước ETL trước nhập | Không: file phải tương thích schema/token semantics |
| Khi source tiếp tục có write mới | CSV snapshot không tự bắt kịp | Snapshot SSTables cũng không tự bắt kịp |
| Verify | Primary keys, values, error records | Source ranges/files, streaming, data/replicas |
| Ưu điểm | Đơn giản cho CSV nhỏ | Hiệu quả khi đã có SSTables hợp lệ |

**Không dùng lab ít rows để công bố công cụ nào “nhanh hơn”.** DSBulk/Spark/COPY/sstableloader phục vụ **đầu vào và bài toán khác nhau**, so sánh performance cần dataset, topology, RF/CL, page size và resource headroom tương đương.

## 19. Java Driver 4.x: importer với prepared statements và cửa sổ in-flight hữu hạn

Nếu CSV cần validation đặc biệt, mapping từ nhiều nguồn, source event IDs hoặc business-version checks, bạn có thể viết **custom Java importer**. Nhưng tự viết đồng nghĩa tự xử lý backpressure, errors, retries, progress và checkpoint. Không tạo một `CqlSession` mới cho mỗi dòng hoặc gọi `executeAsync()` một triệu lần mà không chặn concurrency.

### 19.1. Chuẩn bị dữ liệu đã parse/validate

Giả sử pipeline Java nhận từng `Event` đã được parse từ thư viện CSV chuẩn (Apache Commons CSV/Jackson CSV hoặc tương đương), đã kiểm UUID, ngày, timestamp UTC, decimal, primary key và business rules. **Đoạn sau không phải CSV parser**: nó chỉ chịu trách nhiệm ghi Cassandra.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public final class BoundedEventImporter {
    public record Event(
        String tenantId,
        LocalDate day,
        Instant eventTime,
        UUID eventId,
        String status,
        BigDecimal amount,
        String note
    ) {}

    private static final int MAX_IN_FLIGHT = 16; // Ví dụ LAB
    private final CqlSession session;
    private final PreparedStatement insert;

    public BoundedEventImporter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO bulk_lab.events_by_tenant_day " +
            "(tenant_id, day, event_time, event_id, status, amount, note) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void importEvents(Iterable<Event> source) {
        List<CompletionStage<AsyncResultSet>> window =
            new ArrayList<>(MAX_IN_FLIGHT);

        for (Event row : source) {
            validate(row);

            BoundStatement statement = insert.bind(
                    row.tenantId(),
                    row.day(),
                    row.eventTime(),
                    row.eventId(),
                    row.status(),
                    row.amount(),
                    row.note())
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            window.add(session.executeAsync(statement));
            if (window.size() == MAX_IN_FLIGHT) {
                awaitWindow(window);
            }
        }
        if (!window.isEmpty()) {
            awaitWindow(window);
        }
    }

    private static void validate(Event row) {
        if (row.tenantId() == null || row.tenantId().isBlank()
            || row.day() == null || row.eventTime() == null
            || row.eventId() == null || row.status() == null) {
            throw new IllegalArgumentException("Invalid source record");
        }
    }

    private static void awaitWindow(
            List<CompletionStage<AsyncResultSet>> window) {

        CompletableFuture<?>[] futures = window.stream()
            .map(CompletionStage::toCompletableFuture)
            .toArray(CompletableFuture[]::new);

        // Hoàn tất tối đa MAX_IN_FLIGHT requests trước khi gửi tiếp.
        CompletableFuture.allOf(futures).join();
        window.clear();
    }
}
~~~

Đọc code:

1. `PreparedStatement` được tạo một lần và driver có thông tin routing key khi bind partition key đúng.
2. `MAX_IN_FLIGHT=16` là **giới hạn request đang chờ**, không phải 16 QPS. Tốc độ thực phụ thuộc latency và server load.
3. Khi `allOf().join()` ném exception, **một số requests khác có thể đã thành công**. Không tự đánh dấu cả window failed hoặc complete; pipeline production phải lưu **record IDs + per-request outcome** và xử lý unknown outcomes.
4. `setIdempotent(true)` chỉ là tín hiệu cho **driver retry policy**. Chỉ đặt khi thao tác thực sự idempotent theo business semantics: cùng PK, cùng values/timestamp/TTL chính sách; **không** áp dụng máy móc cho counters/LWT.
5. `CL=ONE` là ví dụ lab RF=1, không khuyến nghị production nhiều replicas. Giữ `LOCAL_QUORUM` hoặc CL bắt buộc của ứng dụng khi thiết kế production.
6. Code giả định `source` đã chuẩn hóa null; một `note=null` có thể có semantics tombstone. Nếu muốn “không cập nhật note” phải dùng **UNSET hoặc statement chỉ chứa cột cần ghi** theo phiên bản/driver, không tự diễn dịch null là bỏ qua.
7. Không ghi source payload/PII vào log metrics. Dùng event ID/checkpoint và error category.

### 19.2. Tại sao code này chỉ là khung importer?

Để chạy production, cần bổ sung:

| Khía cạnh | Việc phải làm |
|---|---|
| Parser | CSV/JSON reader chuẩn, streaming iterator, encoding, schema validation |
| Rate control | Token bucket hoặc adaptive concurrency dựa SLO và pending queues |
| Retry | Exponential backoff, jitter, classify permanent/transient, idempotency |
| Checkpoint | Source offsets/manifest, status per PK/event ID, không ack khi unknown |
| Error sink | Quarantine records malformed; log lỗi đã mask |
| Metrics | Input/accepted/failed/unknown rates, p95/p99, in-flight/retries |
| Credentials | Secrets manager, TLS, least-privilege CQL role |
| Lifecycle | Session reuse/clean shutdown, chờ futures hoàn tất trước close |
| Versions | Cassandra/driver compatibility, prepared statement/schema change |
| Correctness | Backfill/catch-up + audit đối soát, TTL/timestamp/DELETE |

**Không dùng `MAX_IN_FLIGHT` cố định làm toàn bộ cơ chế backpressure** nếu batch source có thể tạo nhiều writers/processes song song: cần giới hạn tổng concurrency của cả job, không chỉ một Java instance.

### 19.3. Giới hạn retries và timeout

Một write timeout ở client không khẳng định Cassandra **chưa ghi**. Có thể coordinator/replica đã xử lý nhưng ACK trễ/mất. Khi retry:

- Giữ source event ID/primary key bất biến.
- Nếu có business sequence/timestamp, bảo vệ thứ tự cập nhật.
- Không tự động kéo `request.timeout` lên mức rất lớn chỉ để làm `COPY`/Java job “khỏi lỗi”.
- Không thay CL vô cớ để tăng throughput.
- Đặt max attempts/backoff và chuyển kết quả **unknown** sang reconciliation.
- Thực hiện retry chọn lọc sau khi cluster ổn định, không tạo retry storm trong thời gian disk/GC bị overload.

### 19.4. Theo dõi đồng thời Java và Cassandra

~~~text
Java:
  source rows/s
  normalized/invalid rows/s
  requests in-flight, successful/failed/unknown
  request p95/p99 by target table + CL
  retries and pool exhaustion

Cassandra:
  ClientRequest.Write.Latency/Timeouts
  Table.WriteLatency, Memtable/CommitLog
  PendingFlushes, PendingCompactions
  node CPU/GC/disk await/network
  replica liveness/ring and disk free

Business:
  unique primary keys loaded
  source-to-target match rate
  CDC catch-up lag / watermark
  must-be-absent DELETE/expired keys
~~~

**Tối ưu thành công** là tăng thông lượng **được xác minh đúng** trên mỗi giờ trong khi vẫn giữ headroom và SLO, không phải chỉ tăng số lệnh `executeAsync` được gửi mỗi giây.

## 20. Các tình huống thực tế khi chọn công cụ hoặc xử lý lỗi

### Ca A — CSV nhỏ, schema khớp, cần demo trong hôm nay

**Đầu vào:** 3.000 rows, 7 cột đơn giản, PK rõ, cluster lab một node.  
**Quyết định:** `cqlsh COPY FROM` là lựa chọn đơn giản, ghi file error và đối chiếu theo PK. Không dựng Spark chỉ để nạp file vài trăm KiB.

**Điểm mấu chốt:** Đơn giản không có nghĩa bỏ baseline; CSV vẫn có thể sai UUID/date/decimal và duplicate PK.

### Ca B — 100 GB CSV với hàng nghìn file và lỗi phải replay có chọn lọc

**Quyết định:** Cân nhắc DSBulk, mapping cụ thể, dry run trên subset, concurrency limit, operation logs và error files. Nếu transformation phức tạp hơn, chọn Spark/custom ETL.  
**Không nên:** Đẩy mọi dòng qua một `cqlsh COPY` rồi không có checkpoint, hoặc tăng `NUMPROCESSES` tới khi cluster timeout.

### Ca C — Dữ liệu đã là SSTables, target topology khác

**Đầu vào:** Snapshot từ ring 3 nodes, target 5 nodes/RF3, cùng partitioner và SSTable format tương thích.  
**Quyết định:** `sstableloader` từ staging, ring-aware streaming theo target replicas.  
**Không nên:** Chép file theo cặp node A→P, B→Q rồi `refresh`.

### Ca D — Bảng cũ partition theo tenant, bảng mới partition theo tenant/day

**Quyết định:** DSBulk/Spark/Java chuyển dữ liệu thành mutations với `day` đúng; `sstableloader` **không thể tự đổi primary key structure** của SSTables cũ.  
**Nguy cơ:** Day bucket theo timezone sai, duplicate event ID hoặc mất sự kiện chạy qua nửa đêm.

### Ca E — Backfill trùng với cập nhật status live

**Tình huống:** Source snapshot giữ `NEW`, ứng dụng vừa cập nhật target thành `PAID`, sau đó `COPY FROM` viết `NEW` lại với timestamp mới.  
**Quyết định:** `STOP`, kiểm event version/watermark, phục hồi đúng những mutation mới và chuyển sang isolated backfill/catch-up.  
**Không nên:** Nạp lại toàn bộ snapshot thêm lần nữa và hy vọng last write wins có nghĩa đúng nghiệp vụ.

### Ca F — Java bulk importer tăng lên 500 in-flight và write timeout bùng nổ

**Giả thuyết:** Coordinator/replica/disk bị quá tải, driver retry tạo thêm attempts.  
**Hành động:** Giảm concurrency có kiểm soát, kiểm `tpstats`, `compactionstats`, disk latency, CL. Không cho importer gửi tiếp triệu futures khi các request cũ chưa thoát.

### Ca G — Nạp đúng hàng nhưng query `WHERE status='PAID'` vẫn chậm

**Lý do:** Bulk loader không thay data model. Nếu `status` chỉ là regular column và truy vấn không có partition key/index phù hợp, câu query có thể phải filtering hoặc bị từ chối.  
**Hành động:** Thiết kế bảng theo query/index phù hợp và benchmark, không đổ lỗi cho `COPY`.

### Ca H — CSV export rồi import lại làm TTL không còn đúng

**Lý do:** CSV không chứa expiration gốc; `COPY FROM` tạo mutation mới theo TTL hiện tại/chính sách target.  
**Hành động:** Ngăn cutover, xác định dữ liệu phải hết hạn, dùng nguồn có metadata đầy đủ hoặc pipeline tính remaining TTL đúng. Không “hồi sinh” session/PII đã phải xóa.

### Ca I — DSBulk ghi error file chứa dữ liệu nhạy cảm

**Rủi ro:** `*.bad` và operation logs có thể chứa raw source lines; chia sẻ file rộng gây rò rỉ.  
**Hành động:** Hạn chế ACL, mã hóa, masking, retention, log level phù hợp, không đưa credential vào command line/process listing nếu có cơ chế secret an toàn.

### Ca J — `sstableloader` kết nối native CQL được nhưng stream fail

**Khả năng:** Storage port/TLS/firewall/broadcast address không thông; source SSTable format/partitioner/schema lỗi.  
**Hành động:** Kiểm `--help`/logs/network tới natural endpoints, không chỉ initial host; giữ backup gốc, không sửa file bằng tay.

### Ca K — DSBulk hoặc Spark báo “100% processed”, nhưng một DC thiếu dữ liệu

**Khả năng:** Quorum local tại dc1 không xác minh dc2, RF/DC config sai, replica từng DOWN hoặc source range coverage thiếu.  
**Hành động:** Đối chiếu topology, logs/repair, xác minh từng DC ở CL phù hợp và lấy mẫu qua token ranges; không coi transport success là replica correctness.

### Ca L — Nạp nhiều SSTables lên cluster sắp đầy disk

**Nguy cơ:** Streaming tạo SSTables mới, compaction cần temporary space, snapshots giữ file cũ, ứng dụng p99 xấu.  
**Quyết định:** Dừng ramp-up, đánh giá disk headroom và capacity; không tự chạy major compaction hoặc xóa SSTable/tombstone để ép chỗ trống.

## 21. Checklist chọn và chạy bulk load an toàn

### 21.1. Trước khi nạp

- [ ] Mục tiêu là **initial load, migration schema, backfill hay restore** đã được xác định rõ.
- [ ] Nguồn là CSV/JSON/Parquet/event log hay SSTable; đã chọn công cụ đúng loại input.
- [ ] Đã có owner/source-of-truth và recovery point/watermark tin cậy.
- [ ] Đã đo số rows, bytes, distinct partition keys, p95/p99 partition size và skew.
- [ ] Schema đích hỗ trợ **truy vấn yêu cầu**, partition key/clustering đã được review.
- [ ] CQL types, UUID/date/timestamp timezone, decimal/collection/UDT mapping đã kiểm.
- [ ] Primary-key fields không null; duplicate/invalid rows có chính sách rõ.
- [ ] Đã xác nhận RF theo DC, CL, ring và natural replica placement.
- [ ] Nếu dùng SSTables: format/partitioner/table schema, file components/checksum và source range coverage đúng.
- [ ] Nếu dùng `sstableloader`: directory `keyspace/table`, initial hosts, storage ports/TLS và staging ổn định.
- [ ] Nếu dùng `COPY`/DSBulk: CSV encoding/header/quoting/NULLVAL và error file được kiểm.
- [ ] Nếu dùng Spark/Java: dependency versions, mapper, concurrency, retry, checkpoint đã thử.
- [ ] Không chạy đồng thời topology change/repair lớn mà chưa có capacity plan.
- [ ] Có baseline p99, throughput, disk/GC, memtable/flush/compaction và replica health.
- [ ] Đã đánh giá timestamps, TTL, tombstone, GDPR/retention và các dữ liệu **phải vắng**.
- [ ] Đã xác định strategy khi writes vẫn đang diễn ra: pause, dual-write/CDC hoặc isolated backfill.
- [ ] Có lab/staging thử với sample và nguồn backup độc lập.
- [ ] Đã định nghĩa trigger `GO/HOLD/STOP` và rollback/escalation.

### 21.2. Trong khi nạp

- [ ] Tool trỏ đúng cluster, local DC, keyspace/table; thông tin target đã được người vận hành xác nhận.
- [ ] Input files/checksums và schema hash được lưu theo run ID.
- [ ] Quá trình nhập chia batch/chunk nhỏ đủ để resume và đối soát.
- [ ] Có giới hạn concurrency/rate, mở rộng theo nấc khi p99 và disk headroom còn tốt.
- [ ] Error parse/type khác write timeout/unknown được xử lý bằng policy riêng.
- [ ] Không xóa/ghi đè error/quarantine files trước khi chúng được đối soát.
- [ ] Không cho `COPY FROM` viết timestamps mới vào bảng live khi có nguy cơ ghi đè newer writes.
- [ ] Không dùng huge cross-partition BATCH hoặc disable CL/repair/tombstone protection để đạt tốc độ.
- [ ] Theo dõi hàng đợi flush/compaction, disk await, node liveness và Java request p99.
- [ ] Có checkpoint của chunks **đã VERIFIED**, không chỉ “processed”.
- [ ] Với SSTable streams, theo dõi per-node/per-DC transfers và file source sets, không chỉ total bytes.

### 21.3. Sau khi nạp

- [ ] Tổng nguồn, parsed, rejected, attempts, confirmed writes và unknown outcomes khớp manifest.
- [ ] Các source chunks/token ranges được kiểm đủ; không có source file bị bỏ sót.
- [ ] PK/column values/version/ordering/TTL/DELETE đúng theo audit.
- [ ] Schema target, indexes/derived tables và query patterns hoạt động như dự kiến.
- [ ] Các natural replicas/DC cần thiết có dữ liệu; repair/backfill xử lý theo runbook.
- [ ] Query families của Java đạt p95/p99, timeout và consistency level ban đầu.
- [ ] Không có backlog compaction/flush tăng không hồi phục hoặc disk headroom thấp.
- [ ] CDC/outbox catch-up lag đạt tiêu chí; writes sau snapshot không bị mất.
- [ ] Canary read/cutover qua feature flag đã kiểm, có phương án quay lại dữ liệu đầy đủ.
- [ ] Đã xác minh trạng thái **must-be-absent** của hàng đã DELETE/TTL-expired.
- [ ] Staging, error logs, source snapshots và credentials được giữ/dọn đúng retention.
- [ ] Báo cáo coverage (full/sampled), RPO/RTO thực, owner và residual risks đã hoàn tất.

## 22. Câu hỏi tự đánh giá

**Câu 1.** Có file CSV 10.000 rows, ít biến đổi và cluster lab một node. Nên bắt đầu với công cụ nào?  
**Định hướng:** `cqlsh COPY FROM` có thể đơn giản nhất nếu schema và type chuẩn, kèm sample/errors/validation.

**Câu 2.** Có SSTables từ cluster A và target B đã đổi số node/RF. Vì sao `sstableloader` phù hợp hơn `nodetool import` trên từng node?  
**Định hướng:** Nó stream theo natural replicas/token ownership của ring đích thay vì local copy tùy ý.

**Câu 3.** DSBulk load có cần bảng đích tồn tại và partition key đúng không?  
**Định hướng:** Có; mapping có thể giúp transform fields nhưng không tự sửa data model hay replica placement.

**Câu 4.** Một CSV có header `tenant_id,day,event_time,...`. Vì sao cần `HEADER = TRUE` với COPY FROM?  
**Định hướng:** Nếu không, dòng tên cột có thể bị parse như một record, gây lỗi type/PK.

**Câu 5.** Vì sao field `"Khách ghi: ""giao sáng"""` không thể tách bằng `String.split(",")`?  
**Định hướng:** CSV có quoting/escaped quotes và có thể chứa dấu phẩy/newline trong field.

**Câu 6.** `COPY TO` rồi `COPY FROM` có bảo toàn tombstones, TTL gốc và write timestamps của từng cell không?  
**Định hướng:** Không; CSV là export logic, không phải SSTable backup.

**Câu 7.** Nguồn có `tenant-a/day21` chứa nhiều triệu events. Tăng `NUMPROCESSES` có giải quyết hot partition không?  
**Định hướng:** Không; natural replica set cho partition vẫn là bottleneck, phải sửa bucket/model workload.

**Câu 8.** DSBulk `--dryRun` có nghĩa cluster đã ghi data chưa?  
**Định hướng:** Không; dùng để kiểm input/mapping trước khi nạp thật.

**Câu 9.** DSBulk `--engine.maxConcurrentQueries 16` giới hạn chính xác 16 rows/s không?  
**Định hướng:** Không; nó giới hạn query concurrency, throughput còn tùy latency và batch.

**Câu 10.** Tại sao Spark job đọc từ Parquet không thể chỉ `repartition(1000)` rồi coi là được load balance trong Cassandra?  
**Định hướng:** Hot partition keys vẫn tập trung vào cùng token/replicas; Spark shuffle không thay Cassandra partition distribution.

**Câu 11.** Khi bảng cũ có `PRIMARY KEY ((tenant_id),...)`, có thể `ALTER TABLE` thêm `day` vào partition key không?  
**Định hướng:** Không; cần bảng mới, backfill và chuyển access pattern.

**Câu 12.** Một update `PAID` đã có ở target T1 nhưng backfill CSV snapshot T0 chứa `NEW` chạy ở T2. Có nguy cơ gì?  
**Định hướng:** COPY tạo mutation timestamp mới hơn, có thể ghi đè PAID bằng NEW.

**Câu 13.** Tại sao retry `UPDATE counter=counter+1` không idempotent giống reimport row có stable key?  
**Định hướng:** Counter increment có thể bị áp dụng nhiều lần, tạo giá trị sai.

**Câu 14.** Nếu client timeout, importer có thể đánh dấu write “chưa diễn ra” ngay không?  
**Định hướng:** Không; ACK có thể mất dù replica đã ghi, cần unknown outcome reconciliation.

**Câu 15.** TTL 3600 từ 90 phút trước khi import lại CSV: tại sao `USING TTL 3600` khi import là sai nếu muốn giữ expiration gốc?  
**Định hướng:** Nó có thể cho dữ liệu sống thêm 1 giờ mới, thay vì đã hết hạn.

**Câu 16.** Một stream SSTable đã nạp xong nhưng `SELECT` trả 0 rows. Kể ít nhất ba khả năng.  
**Định hướng:** Sai source ranges/schema/PK, TTL đã expire, tombstone mới hơn che, đọc DC chưa đủ.

**Câu 17.** Vì sao `COUNT(*)` khớp không đủ để nghiệm thu migration?  
**Định hướng:** Có thể sai primary keys/values/timestamps/deletes, hoặc tác động lớn lên cluster khi scan.

**Câu 18.** `LOCAL_QUORUM` ở dc1 thành công có xác nhận dc2 đủ dữ liệu không?  
**Định hướng:** Không. Local quorum chỉ xét trong DC cục bộ.

**Câu 19.** Tại sao phải giữ snapshot/backup gốc trước khi chạy `sstableloader`?  
**Định hướng:** Staging/streaming/upgrade có thể phát sinh lỗi, cần integrity và khả năng thử lại; backup là nguồn khôi phục.

**Câu 20.** Khi Java importer đạt 16 in-flight, đoạn code nên làm gì trước khi gửi thêm?  
**Định hướng:** Chờ/quan sát window hoàn tất, giới hạn concurrency; không tạo vô hạn futures.

**Câu 21.** Sau dual-write, V1 ngừng nhận writes trong 48 giờ, có thể rollback read flag về V1 ngay không?  
**Định hướng:** Không nếu V1 thiếu delta mới; cần reverse sync/replay/validation trước.

**Câu 22.** Importer có 1.000 rows processed, 998 writes confirmed và 2 timeout unknown. Có được đánh dấu chunk VERIFIED chưa?  
**Định hướng:** Chưa; phải xử lý/đối soát hai outcomes không chắc chắn.

**Câu 23.** Vì sao không nên dùng one giant logged batch để tăng tốc nạp nhiều partitions?  
**Định hướng:** Batchlog/coordinator overhead, latency/timeouts và không phải SQL bulk transaction.

**Câu 24.** Khi compaction backlog tăng sau streaming nhưng read/write SLA chưa vượt, có cần dừng ngay không?  
**Định hướng:** Xem trend/capacity và điều kiện thoát backlog, không dựa một snapshot; nếu disk/SLO bị đe dọa thì throttle/stop.

## 23. Tổng kết

~~~text
                    KẾ HOẠCH NẠP DỮ LIỆU
                              |
                    Phân loại NGUỒN
               /              |              \
           CSV/JSON         SSTables       ETL/Event log
              |                |               |
       COPY / DSBulk      sstableloader     Spark / Java
              |                |               |
       Typed mutations    Replica stream   Validated mutations
               \              |              /
                \             |             /
                  SCHEMA / PARTITION KEY
                             |
                     TARGET RING / RF / CL
                             |
                RATE LIMIT + CHECKPOINT
                             |
              +--------------+--------------+
              |              |              |
           TRANSPORT      REPLICA         BUSINESS
           ERRORS         COVERAGE        CORRECTNESS
              |              |              |
              +--------------+--------------+
                             |
                       CATCH-UP / CUTOVER
                             |
                     ROLLBACK WINDOW
                             |
                    MIGRATION_VALIDATED
~~~

**Nguyên tắc quan trọng nhất:** Chọn bulk loader theo **dữ liệu nguồn và mục tiêu di chuyển**, không theo khẩu hiệu “tool nào nhanh nhất”. `cqlsh COPY` tiện cho CSV nhỏ/vừa, DSBulk hỗ trợ mapping/log lỗi và concurrency, Spark cho ETL phân tán, Java Driver cho pipeline có nghiệp vụ riêng, còn `sstableloader` stream SSTables tới natural replicas của ring đích. Tất cả chỉ đáng tin khi **schema/partition key, timestamp/TTL, idempotency, RF/DC, SLO và audit đối soát** được xử lý có kiểm soát. Nạp được file là **bắt đầu của validation**, không phải kết thúc migration.

## Tài liệu tham khảo

- [Apache Cassandra — cqlsh COPY TO/FROM](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html) — syntax, `HEADER`, `NULLVAL`, `INGESTRATE`, `ERRFILE`, `MAXATTEMPTS` và các giới hạn COPY.
- [Apache Cassandra — Bulk Loading](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/bulk_loading.html) — `sstableloader`, cấu trúc staging, `nodetool import` và stream theo replication.
- [Apache Cassandra — sstableloader](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/sstable/sstableloader.html) — `--nodes`, `--throttle-mib`, native/streaming ports và source SSTables.
- [Apache Cassandra — nodetool import](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/import.html) — local import, token verification và repaired metadata.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — thiết kế theo truy vấn, partition key, clustering key và denormalization.
- [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `INSERT`, `UPDATE`, `USING TIMESTAMP`, `USING TTL`, `BATCH` và CQL semantics.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — `ClientRequest`, `Table`, memtable, compaction và thread pools.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — replica convergence và giới hạn repair.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — DELETE/TTL, grace và zombie data.
- [DataStax Bulk Loader — Load data](https://docs.datastax.com/en/dsbulk/developing/simple-load.html) — `dsbulk load`, CSV/JSON mapping và `--dryRun`.
- [DataStax Bulk Loader — Engine options](https://docs.datastax.com/en/dsbulk/reference/engine-options.html) — `--engine.maxConcurrentQueries` và điều tiết nguồn tải.
- [DataStax Bulk Loader — Logging options](https://docs.datastax.com/en/dsbulk/reference/logging-options.html) — operation logs, `connector.bad`, `mapping.bad` và `load.bad`.
- [Apache Spark Cassandra Connector — DataFrames](https://github.com/apache/cassandra-spark-connector/blob/trunk/doc/14_data_frames.md) — `format("cassandra")`, `keyspace`, `table` và API reads/writes.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — bind metadata, routing keys và prepared CQL.
- [DataStax Java Driver 4.17 — Query idempotence](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/idempotence/) — xác định idempotent statements và rủi ro retry.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — session/node metrics, timeouts và request latency.

