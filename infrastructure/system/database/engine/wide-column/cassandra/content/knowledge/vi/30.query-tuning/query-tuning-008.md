# Giảm collection lớn, phân vùng lớn và tỷ lệ tombstone

> **Chương:** Tối ưu truy vấn  
> **Phạm vi:** Apache Cassandra, cơ sở dữ liệu phân tán theo mô hình *wide-column*, với trọng tâm thiết kế bảng theo truy vấn và giảm *read amplification*. Ví dụ thực hành gồm CQL, `nodetool` và Cassandra Java Driver 4.x.
>
> **Mục tiêu học tập:** Nhận biết ba nguồn gây truy vấn chậm — **collection quá lớn**, **partition quá rộng** và **tombstone bị quét nhiều** — rồi thiết kế lại partition/clustering key, TTL, thao tác cập nhật/xóa và đường đọc. Phân biệt dữ liệu “không còn xuất hiện” với dữ liệu đã được thu hồi vật lý.

## 1. Tình huống: `LIMIT 20` nhưng vẫn chậm

Một API đọc 20 sự kiện mới nhất của một khách hàng:

```cql
SELECT event_time, event_id, payload
FROM lab.customer_events_unbounded
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
LIMIT 20;
```

Câu truy vấn có đủ partition key và trả rất ít hàng, nhưng p99 tăng lên hàng trăm mili giây. Trong bảng:

- Một khách hàng có thể tích lũy nhiều năm sự kiện trong **cùng một partition**.
- Mỗi sự kiện giữ một `set<text>` có hàng nghìn tag, một `map<text,text>` ngày càng lớn và một `list<text>` ghi lịch sử thao tác.
- Hệ thống dùng TTL ngắn cho một số cell, xóa hàng cũ thường xuyên và cập nhật collection nhiều lần.
- Các SSTable chứa dữ liệu sống xen tombstone; compaction không kịp thu hồi hoặc chưa đủ điều kiện thu hồi.

**`LIMIT 20` chỉ giới hạn số hàng kết quả**, không cam kết Cassandra chỉ phải duyệt 20 hàng/cell vật lý. Replica có thể phải tra nhiều SSTable, bỏ qua hàng nghìn dữ liệu đã xóa/hết TTL hoặc xử lý một partition rất rộng trước khi tìm đủ hàng còn sống.

Cần giải quyết theo ba lớp:

1. **Đổi mô hình dữ liệu** để collection/partition có giới hạn tăng trưởng.
2. **Giảm sinh tombstone không cần thiết** và đọc ít dữ liệu đã chết.
3. **Đo trước/sau** bằng độ trễ client, số tombstone scanned, kích thước partition, SSTable và tải compaction/repair.

Tối ưu Cassandra thường bắt đầu bằng **đường truy vấn nghiệp vụ**, không bắt đầu bằng cách tăng heap hay timeout.

## 2. Hiểu ba vấn đề khác nhau

| Vấn đề | Đơn vị tăng trưởng | Hệ quả phổ biến | Hướng tối ưu ưu tiên |
| --- | --- | --- | --- |
| **Collection lớn** | Số phần tử hoặc số byte trong một cột collection | Mutation/đọc/cập nhật collection nặng; xóa/thay thế có thể sinh tombstone | Chỉ dùng collection nhỏ, có giới hạn; với dữ liệu tăng liên tục chuyển thành bảng theo truy vấn |
| **Partition lớn** | Số row/cell và tổng byte dưới cùng partition key | Truy vấn đụng rất nhiều SSTable/cell; hotspot, compaction/streaming/repair khó | Bucket theo thời gian/nhóm/shard và truy vấn đúng partition |
| **Tombstone nhiều** | Số cell, row, range hoặc partition deletion marker phải xem xét | Quét nhiều dữ liệu chết để tìm kết quả còn sống; p99/timeout tăng | Giảm xóa và TTL không đồng nhất; chọn retention/bucketing/compaction phù hợp |

Ba vấn đề có thể khuếch đại nhau: một partition không giới hạn chứa collection lớn; collection bị thay thế thường xuyên tạo tombstone; query mới phải hòa giải nhiều SSTable và dữ liệu đã chết.

### Không có một “ngưỡng thần kỳ” cho mọi cluster

Không thể tuyên bố một collection có đúng 100 phần tử là an toàn, 101 phần tử là nguy hiểm; cũng không có một kích thước partition lý tưởng dùng cho mọi workload. Cần tính cả:

- Kích thước trung bình và **phân vị cao nhất** của phần tử/row.
- Đọc toàn collection hay chỉ đọc một phần.
- Tốc độ update/delete, TTL, phân bố key nóng/lạnh.
- Số SSTable, I/O, RF, network và latency SLO.
- Cách partition được truy vấn: một key hay nhiều key mỗi request.

Mục tiêu là **tăng trưởng bị chặn và chi phí truy vấn dự báo được** qua thời gian.

## 3. Collections trong Cassandra: phù hợp khi nhỏ và hữu hạn

CQL hỗ trợ `list`, `set` và `map` để biểu diễn nhóm giá trị. Chúng hữu ích khi tập phần tử nhỏ, gắn chặt vòng đời và cách truy vấn với một row.

Ví dụ bảng metadata nhỏ, số cờ và thuộc tính được giới hạn:

```cql
CREATE TABLE IF NOT EXISTS lab.event_small_metadata (
    event_id uuid PRIMARY KEY,
    flags set<text>,
    attributes map<text, text>
);
```

Cập nhật từng phần tử trên **non-frozen collection** khi cú pháp và kiểu cho phép:

```cql
UPDATE lab.event_small_metadata
SET flags = flags + {'important'},
    attributes['source'] = 'mobile'
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

Với các cấu trúc nhỏ, cố định về số phần tử, collection có thể đơn giản hơn tạo bảng phụ. Nhưng khi phần tử tăng cùng thời gian hoạt động của khách hàng, collection trở thành một cấu trúc khó kiểm soát.

### So sánh ba kiểu

| Kiểu | Đặc trưng | Khi nên cân nhắc | Rủi ro nếu không giới hạn |
| --- | --- | --- | --- |
| `set<text>` | Các phần tử duy nhất, không bảo đảm thứ tự nghiệp vụ | Cờ, quyền hoặc tag **rất ít và có giới hạn** | Set lớn, thao tác xóa/thay thế nhiều và truy vấn lấy toàn bộ |
| `map<text,text>` | Khóa → giá trị; có thể thay đổi phần tử riêng lẻ khi không frozen | Thuộc tính linh hoạt nhưng số khóa được quản lý | Map thành kho key-value tăng liên tục, đọc hàng nghìn mục |
| `list<text>` | Danh sách có thứ tự với các thao tác cập nhật phụ thuộc biểu diễn collection | Danh sách nhỏ, thực sự cần thứ tự | Lịch sử append vô hạn, cập nhật/xóa phần tử và xung đột đồng thời phức tạp |

**Đừng dùng `list` để lưu toàn bộ lịch sử event trong một row.** Nếu nghiệp vụ cần truy vấn gần đây, phân trang, lọc thời gian hoặc lưu hàng triệu event, một bảng có clustering key sẽ phù hợp hơn.

## 4. Non-frozen và frozen: khác ở cập nhật, không phải phép màu giảm kích thước

Cassandra hỗ trợ collection dạng **non-frozen** và **frozen** trong những ngữ cảnh cú pháp/kiểu dữ liệu được phép. Cách triển khai cụ thể và hạn chế thay đổi theo phiên bản.

### Non-frozen collection

Về mặt khái niệm, các phần tử collection có thể được lưu thành các cell riêng có metadata, cho phép cập nhật một phần.

```cql
CREATE TABLE lab.event_metadata_mutable (
    event_id uuid PRIMARY KEY,
    attributes map<text, text>
);
```

Thao tác cập nhật khóa nhỏ:

```cql
UPDATE lab.event_metadata_mutable
SET attributes['priority'] = 'high'
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

Đây thường hợp lý hơn việc thay **toàn bộ map** khi chỉ thay một mục. Tuy nhiên, số phần tử tăng không giới hạn vẫn gây chi phí đọc và các phiên bản/tombstone khi xóa hoặc ghi đè.

### Frozen collection

```cql
CREATE TABLE lab.event_metadata_frozen (
    event_id uuid PRIMARY KEY,
    attributes frozen<map<text, text>>
);
```

Collection frozen được xem như một giá trị ở mức cell: không thể cập nhật riêng từng phần tử theo cách non-frozen; thường phải ghi lại cả collection khi thay đổi. Điều này có thể phù hợp dữ liệu nhỏ, ổn định, được thay thế nguyên khối.

**Không dùng `frozen` để “sửa” collection khổng lồ.** Một collection lớn được đóng băng vẫn là một giá trị lớn phải truyền, giải mã và ghi lại khi thay đổi; nó chỉ đổi mô hình cập nhật/lưu trữ.

### Collection có thể sinh tombstone khi nào?

- Xóa một phần tử khỏi `set`/`map` hoặc xóa toàn bộ collection.
- Thay thế nguyên collection và che các phần tử/phiên bản trước đó trong trường hợp liên quan.
- Ghi giá trị `null` cho cột theo ngữ nghĩa CQL/driver tương ứng.
- TTL của cell/collection element hết hạn hoặc cập nhật làm dữ liệu cũ trở nên obsolete.

**Không phải mọi thao tác thêm một phần tử đều là một tombstone.** Mức tombstone thực tế phụ thuộc phép ghi, timestamp, collection type và phiên bản; phải kiểm chứng bằng metrics/tracing nếu nghi ngờ.

## 5. Khi nào nên chuyển collection thành bảng riêng?

Hãy tách collection nếu một hay nhiều câu sau là đúng:

1. Số phần tử **có thể tăng vô hạn** cùng hoạt động của người dùng.
2. Cần **đọc một trang**, một khoảng thời gian hoặc một nhóm phần tử thay vì toàn bộ collection.
3. Phần tử có vòng đời, TTL hoặc quyền truy cập khác nhau.
4. Phần tử được cập nhật/xóa riêng, thường xuyên.
5. Collection xuất hiện trong một row/partition vốn đã rất rộng.
6. Có yêu cầu truy vấn theo phần tử: “tìm event có tag X”, “liệt kê attributes mới nhất”.

Ví dụ thay `set<text> tags` lớn bằng bảng:

```cql
CREATE TABLE lab.event_tags_by_event (
    event_id uuid,
    tag text,
    PRIMARY KEY ((event_id), tag)
);
```

Thêm tag:

```cql
INSERT INTO lab.event_tags_by_event (event_id, tag)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'important'
);
```

Đọc tags của event:

```cql
SELECT tag
FROM lab.event_tags_by_event
WHERE event_id = 11111111-1111-4111-8111-111111111111;
```

Bảng này phù hợp khi số tag **trên mỗi event vẫn có giới hạn nghiệp vụ**. Nếu một event có thể chứa hàng triệu tag, partition key `event_id` lại trở thành partition lớn. Bảng riêng **không tự động bảo đảm partition nhỏ**; vẫn phải chọn partition/bucket theo cardinality và query.

### Nếu query là “tìm sự kiện theo tag”?

Bảng `event_tags_by_event` chỉ hỗ trợ hướng truy vấn từ event → tags. Để tìm tag → events, có thể cần thêm projection theo truy vấn:

```cql
CREATE TABLE lab.events_by_tag_day (
    tag text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    customer_id uuid,
    PRIMARY KEY ((tag, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Query:

```cql
SELECT event_time, event_id, customer_id
FROM lab.events_by_tag_day
WHERE tag = 'important' AND event_day = '2026-11-21'
LIMIT 50;
```

Cách làm này giúp Cassandra đọc theo partition key, nhưng application phải duy trì hai hướng dữ liệu. Ghi projection bổ sung **không mặc nhiên có giao dịch nguyên tử đa bảng/đa partition**; cần thiết kế tính nhất quán, retry idempotent, đối soát và retention.

Nếu một tag đặc biệt phổ biến tạo hàng triệu event/ngày, cần chia tiếp theo giờ/shard, hoặc thay chiến lược truy vấn. Tách collection không thay thế bài toán **phân phối tải**.

## 6. Partition lớn: vì sao Cassandra xử lý khó?

Partition là tập các row có **cùng partition key**. Các row được sắp xếp bằng clustering columns trong partition. Dữ liệu của một partition có thể trải qua nhiều SSTable bất biến, nhiều phiên bản và tombstone.

Giả sử thiết kế ban đầu:

```cql
CREATE TABLE lab.customer_events_unbounded (
    customer_id uuid,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    tags set<text>,
    attributes map<text, text>,
    notes list<text>,
    PRIMARY KEY ((customer_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Partition key chỉ có `customer_id`. Nếu một khách hàng tạo hàng triệu event/năm, **mọi event của khách hàng đó** đi vào cùng một partition bất kể hệ thống đã lưu bao lâu.

Điều này làm tăng:

- Kích thước dữ liệu partition và metadata phục vụ đọc.
- Thời gian scan/clustering range khi truy vấn lịch sử.
- Chi phí compaction vì nhiều SSTable/phiên bản của cùng partition.
- Độ lệch tải: khách hàng rất hoạt động tạo *hot partition*.
- Chi phí streaming, repair, snapshot và phục hồi khi partition quá lớn.
- Áp lực tombstone nếu dữ liệu cũ bị xóa từng row/TTL.

Lưu ý **một partition lớn không có nghĩa dữ liệu luôn nằm nguyên trong một SSTable duy nhất**. Một partition có thể xuất hiện ở nhiều SSTable do quá trình ghi/flush, và một SSTable cũng chứa nhiều partition.

### Kích thước trung bình dễ che phần đuôi

Giả sử có 1 triệu khách hàng:

- 999.000 khách hàng chỉ có vài trăm event.
- 1.000 khách hàng doanh nghiệp có hàng chục triệu event.

Kích thước partition **trung bình** có thể không bất thường, nhưng nhóm partition nóng/lớn tạo phần lớn I/O và p99. Hãy đo **phân phối kích thước partition**, histogram và các partition ngoại lệ, không chỉ total disk space chia tổng partition.

## 7. Chia partition theo bucket thời gian

Khi query là “xem sự kiện trong một ngày/giờ” hoặc “20 sự kiện gần nhất”, có thể thêm bucket vào partition key:

```cql
CREATE TABLE lab.customer_events_by_day (
    customer_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((customer_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Bây giờ mỗi khách hàng có **một partition cho mỗi ngày có sự kiện**, thay vì một partition chứa toàn bộ lịch sử. Query:

```cql
SELECT event_time, event_id, event_type, payload
FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
LIMIT 20;
```

### Bucketing có tác dụng vì lý do nào?

- Giới hạn số event/byte trong **một partition theo cửa sổ thời gian** nếu tốc độ ghi nằm trong dự báo.
- Giúp ứng dụng xác định phạm vi đọc và không duyệt cả lịch sử của khách hàng.
- Giảm tác động của partition cực lớn khi flush/compaction/repair/streaming.
- Có thể hỗ trợ xóa dữ liệu theo retention khi phối hợp TTL/time-window và dữ liệu không cập nhật cũ.

Nhưng đổi lại:

- Query xuyên nhiều ngày phải đọc **nhiều partition**, thường do ứng dụng điều phối và hợp nhất.
- Cửa sổ quá nhỏ có thể tạo quá nhiều partition/round-trip.
- Bucket ngày vẫn quá lớn với khách hàng cực nóng.
- Cần thống nhất cách tính `event_day` từ `event_time`, múi giờ (thường UTC) và xử lý late event.

**Cassandra không tự nối các partition thành một dòng thời gian duy nhất** chỉ vì chúng cùng `customer_id`. Đây là trách nhiệm thiết kế đường đọc.

### Chọn ngày, giờ hay shard?

Ví dụ cần cân nhắc sơ bộ:

```text
Khách hàng lớn: 200 event/giây
Mỗi event:     ~1 KiB dữ liệu logic

Theo ngày:
  200 × 86.400 ≈ 17.280.000 event/ngày
  ≈ 16,5 GiB/ngày (chỉ payload giả định)

Theo giờ:
  200 × 3.600 = 720.000 event/giờ
  ≈ 703 MiB/giờ

Theo giờ + 16 shard phân phối tương đối đều:
  ≈ 44 MiB/partition trong một giờ
```

Đây là **ước lượng dữ liệu logic**, không phải dự báo SSTable byte chính xác. Compression, metadata, cột lớn, replica, compaction và cách shard phân phối có thể làm số thực khác. Các số cũng **không phải ngưỡng Cassandra mặc định**.

Nếu giờ vẫn quá lớn, mô hình `(customer_id, event_hour, shard)` có thể phù hợp, nhưng truy vấn “20 sự kiện mới nhất” phải đọc/merge các shard rồi sắp xếp theo `event_time`. Tăng shard là trao đổi **độ phức tạp đọc** lấy **phân phối tải/partition size tốt hơn**.

### Mẫu thiết kế có shard (khi thật cần)

```cql
CREATE TABLE lab.customer_events_by_hour_shard (
    customer_id uuid,
    event_hour timestamp,
    shard smallint,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((customer_id, event_hour, shard), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Ứng dụng có thể tính `shard` ổn định bằng hash của `event_id` modulo số shard, nhưng phải thống nhất thuật toán và số shard qua mọi writer/reader. **Không tự thay modulo 16 thành 32 giữa chừng** nếu không có versioning/migration, vì reader sẽ không còn biết tìm event cũ ở đâu.

Để đọc dữ liệu gần nhất, ứng dụng lấy theo các shard của giờ cần thiết và merge theo khóa thời gian. Cần giới hạn fan-out và số kết quả đọc từ mỗi shard.

## 8. Đo partition size trước khi chỉnh schema

Một phương pháp có kiểm soát là đo cả ba thứ:

1. **Phân phối partition size:** median, p95/p99, max; chú ý partition hotspot.
2. **Row/cell count trong partition:** một partition có row nhỏ nhưng cực nhiều row vẫn có thể chậm.
3. **Chi phí query:** read latency, tombstone scanned, SSTable reads và số row thực trả về.

Trên node lab có quyền:

```bash
nodetool tablestats lab.customer_events_unbounded
nodetool tablehistograms lab.customer_events_unbounded
```

Tùy phiên bản Cassandra, `tablestats` cho biết thống kê theo bảng như SSTable count, disk space, memtable, read/write latency, tombstone scanned và một số thông tin partition; `tablehistograms` có thể hiển thị histogram về partition size, cell count và latency.

Không lấy tên/cột của một phiên bản làm hợp đồng bất biến cho mọi phiên bản. Khi cần phân tích chi tiết file, công cụ `sstablemetadata` và các công cụ SSTable phù hợp có thể hỗ trợ **trong môi trường lab hoặc theo runbook**; không mở, sửa hay xóa thủ công SSTable của node đang phục vụ.

### Bảng tín hiệu cần quan sát

| Tín hiệu | Nếu tăng thì nghĩ tới | Kiểm tra chéo |
| --- | --- | --- |
| Max/p99 partition size | Khách hàng nóng, key thiếu bucket | Truy vấn theo key nào, số event/ngày |
| SSTable count/read amplification | Nhiều flush, compaction backlog | Pending compactions, disk I/O |
| Read p99 | Đường đọc nặng hoặc replica chậm | GC, CPU, disk, coordinator, CL |
| Rows returned rất ít nhưng tombstones scanned nhiều | Scan dữ liệu chết | TTL/delete pattern, tombstone age |
| Compaction backlog | Dữ liệu cũ khó hợp nhất, tài nguyên bị cạnh tranh | Disk headroom, flush, repair |
| Streaming/repair kéo dài | Phạm vi dữ liệu/partition lớn hoặc node quá tải | Token ranges, disk/network throughput |

Một bảng nhiều partition nhỏ và một vài partition cực lớn có thể cần **tối ưu khóa phân vùng**, không nhất thiết chuyển compaction strategy.

## 9. Tombstone đến từ đâu?

Trong Cassandra, `DELETE` thường ghi một **dấu xóa** thay vì tìm rồi xóa ngay dữ liệu trong SSTable bất biến. Dấu xóa phải che những phiên bản cũ ở SSTable và replica khác cho đến khi an toàn để thu hồi.

Nguồn phổ biến:

| Nguồn | Ví dụ | Vì sao liên quan tuning |
| --- | --- | --- |
| Xóa cột | `DELETE payload FROM ...` | Tạo dấu xóa cell trong cùng partition |
| Xóa row | `DELETE FROM ... WHERE full_primary_key = ...` | Row tombstone cần được hòa giải trên đường đọc |
| Xóa phạm vi clustering | Xóa dải thời gian theo cú pháp phù hợp | Range tombstone có thể ảnh hưởng scan trên dải rộng |
| Xóa partition | Xóa với partition key khi schema/operation cho phép | Partition tombstone che các row cũ trong partition |
| TTL hết hạn | `INSERT ... USING TTL 3600` | Cell hết hạn logic; metadata expiration cần xử lý GC |
| Ghi `null` khi có ngữ nghĩa xóa | Ứng dụng bind null thay vì “không cập nhật” | Dễ tạo tombstone ngoài dự kiến |
| Collection update/delete | Thay/xóa map, set, list hoặc phần tử | Có thể phát sinh tombstone theo phần tử/collection |
| Ghi đè nhiều lần | Cùng cell thay phiên bản, có delete ở giữa | Tăng dữ liệu cần hòa giải tới khi compaction |

**Không đánh đồng mọi cập nhật với một tombstone tường minh.** Ghi đè giá trị thường tạo phiên bản cũ bị che khuất; thao tác delete, TTL và một số thao tác collection mới liên quan trực tiếp đến dấu xóa. Dù vậy, cả phiên bản obsolete và tombstone đều có thể tăng chi phí compaction.

### Đọc logic và dữ liệu vật lý

Sau `DELETE` hoặc TTL expiration, một `SELECT` có thể không trả row/cell. Nhưng SSTable cũ vẫn chứa dữ liệu/metadata cần hợp nhất; tombstone không thể bị bỏ chỉ vì query đã không nhìn thấy.

`gc_grace_seconds` là một điều kiện xét tuổi tombstone; compaction còn phải kiểm tra khả năng còn dữ liệu cũ ở SSTable khác. Ở cấp cluster, repair giúp replica không bỏ lỡ delete trước khi tombstone bị purge, tránh dữ liệu *zombie* sống lại.

## 10. “Tỷ lệ tombstone” nên đo thế nào?

Cassandra không có một chỉ số duy nhất tên **tombstone ratio** mang cùng định nghĩa trên mọi phiên bản, query và monitoring stack. Trong tuning, nên tách:

- **Tombstones scanned per query/read:** số dấu xóa phải xem xét để phục vụ một đọc.
- **Live cells/rows scanned:** số dữ liệu còn sống thực sự phải xem xét, nếu công cụ hỗ trợ.
- **Rows returned:** số hàng gửi cho client, **không đồng nghĩa** số live cells đã đọc.
- **SSTable tombstone/expired share:** tỷ lệ dữ liệu chết ở storage; có thể khác xa tỷ lệ tombstone đọc của một query.

Nếu một phép đo cung cấp đồng thời số tombstone scanned và live cells scanned của cùng phạm vi và định nghĩa, có thể dùng tỷ lệ **tham khảo**:

```text
Tỷ lệ tombstone trong các cell đã scan
= tombstone_scanned / (tombstone_scanned + live_cells_scanned)
```

Ví dụ **giả định**, 4.000 tombstone và 100 live cell trong cùng phép đọc thì tỷ lệ xấp xỉ 97,6%. Nhưng nếu công cụ chỉ trả “20 rows returned”, không được lấy 20 làm `live_cells_scanned` để khẳng định tỷ lệ 99,5%: một row có thể gồm nhiều cell và scan nhiều hơn số trả về.

### Những chỉ số thực tế có ích

- `nodetool tablestats`: ví dụ **average/max tombstones per slice (last five minutes)** hoặc các metric tương đương, tùy release.
- Histograms/JMX read latency và tombstone-scanned nếu exporter hỗ trợ.
- CQL tracing trên **mẫu query** có chi phí cao để quan sát đường đọc.
- Thống kê compaction, SSTable, expired/TTL khi có công cụ phù hợp.
- Client p95/p99, timeout, rows returned và concurrency.

Một truy vấn trả 20 hàng nhưng quét hàng chục nghìn tombstone là tín hiệu cần kiểm tra **query pattern và mô hình dữ liệu**. Trái lại, số tombstone tổng lớn trên đĩa không nhất thiết làm chậm mọi query nếu các partition/query không đọc tới chúng.

### Threshold warning và failure

Nhiều phiên bản Cassandra có cấu hình ngưỡng cảnh báo/thất bại khi đọc quá nhiều tombstone, ví dụ các tham số `tombstone_warn_threshold` và `tombstone_failure_threshold`. Tên, giá trị mặc định và hành vi có thể khác giữa phiên bản hoặc bản phân phối.

Khi thấy cảnh báo:

1. Xác định query, partition/range và số tombstone được quét.
2. Kiểm tra TTL, delete/collection operations và SSTable count.
3. Xem deadline, consistency level, replica chậm và query p99.
4. Thiết kế lại truy vấn/retention trước khi thay ngưỡng.

**Tăng threshold không làm tombstone biến mất.** Nó có thể che triệu chứng hoặc cho phép query tốn tài nguyên hơn, gây ảnh hưởng hàng đợi/đĩa của các request khác.

## 11. Thực hành CQL: TTL và DELETE tạo dữ liệu chết

Các ví dụ sau dành cho **keyspace `lab` đã tồn tại trong môi trường học tập**; không chạy xóa/đổi TTL trên production chỉ để thử.

### Bước A — Tạo bảng bucket ngày

```cql
CREATE TABLE IF NOT EXISTS lab.customer_events_by_day (
    customer_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((customer_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

### Bước B — Ghi TTL ngắn cho một event

```cql
INSERT INTO lab.customer_events_by_day
  (customer_id, event_day, event_time, event_id, event_type, payload)
VALUES
  (aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
   '2026-11-21',
   '2026-11-21T03:00:00Z',
   11111111-1111-4111-8111-111111111111,
   'detail',
   'expires after 1 day')
USING TTL 86400;
```

`event_day` và `event_time` là dữ liệu của event; TTL được tính theo thời điểm mutation được ghi theo cơ chế Cassandra, **không tự lấy mốc từ cột `event_time`**. Khi bản ghi hết TTL, nó không còn sống logic, nhưng có thể vẫn đóng góp dữ liệu chết trên SSTable tới khi GC/compaction thích hợp.

### Bước C — Ghi bản sống lâu hơn

```cql
INSERT INTO lab.customer_events_by_day
  (customer_id, event_day, event_time, event_id, event_type, payload)
VALUES
  (aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
   '2026-11-21',
   '2026-11-21T03:01:00Z',
   22222222-2222-4222-8222-222222222222,
   'audit',
   'retain for 30 days')
USING TTL 2592000;
```

Hai row cùng partition ngày có TTL khác nhau. Chúng có thể nằm cùng SSTable và làm việc bỏ nguyên SSTable khó hơn: 1 ngày sau event đầu đã expired nhưng event thứ hai còn sống. Tách retention class hoặc thống nhất TTL theo bảng/cửa sổ có thể giúp khả năng thu hồi khi workload phù hợp.

### Bước D — Đọc TTL còn lại và xóa có kiểm soát

```cql
SELECT event_time, event_id, payload, TTL(payload)
FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
LIMIT 20;
```

Sau đó xóa **một row cụ thể** trong lab:

```cql
DELETE FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T03:00:00Z'
  AND event_id = 11111111-1111-4111-8111-111111111111;
```

Dữ liệu không còn xuất hiện không chứng minh SSTable đã được thu hồi. Đừng ép compaction hoặc hạ `gc_grace_seconds` bằng 0 để “xóa ngay”; việc đó có thể tạo rủi ro zombie data nếu replica từng bỏ lỡ delete.

## 12. Giảm tombstone từ thiết kế retention

### Cách A — Không tạo dữ liệu rồi xóa hàng loạt nếu có thể tránh

Nếu mỗi ngày thêm vài triệu event và cuối tuần xóa từng row để giữ đúng 7 ngày, hệ thống có thể liên tục tạo nhiều row tombstone.

Thay bằng TTL khi yêu cầu nghiệp vụ cho phép: ghi event có `USING TTL` ngay từ đầu. Tuy nhiên **TTL không phải cơ chế không sinh tombstone**; nó chỉ đưa chính sách hết hạn vào mutation và có thể đơn giản hóa việc lưu trữ/retention.

Cần phân tích xem TTL có đồng nhất không, compaction có cơ hội thu hồi SSTable hay không, và khi nào dữ liệu phải biến mất khỏi kết quả đọc.

### Cách B — Tách nhóm TTL khác nhau

Đừng trộn 1 ngày và 90 ngày trong cùng lớp dữ liệu nếu có thể tách theo query và retention. Một bảng `recent_events` TTL 1 ngày và bảng `audit_events` TTL 90 ngày có thể cho phép các SSTable có vòng đời đồng đều hơn.

Đổi lại, khi API cần tất cả event trong một khoảng, ứng dụng có thể phải đọc/merge nhiều bảng; đây là **đánh đổi thiết kế dữ liệu theo truy vấn**.

### Cách C — TWCS cho time-series append-only phù hợp

**TimeWindowCompactionStrategy (TWCS)** tổ chức compaction theo cửa sổ thời gian, hữu ích cho dữ liệu time-series chủ yếu append-only, TTL tương đối đồng đều và ít update/delete bản ghi cũ.

Khi mọi dữ liệu trong SSTable đã hết TTL và đạt điều kiện GC/an toàn, có cơ hội loại bỏ **cả tệp** thay vì ghi lại từng cell. Nhưng:

- **Không** được kết luận TWCS tự xóa mọi tombstone.
- Backfill, ghi trễ, update dữ liệu cũ và TTL hỗn hợp có thể phá giả định cửa sổ.
- `gc_grace_seconds`, SSTable overlap, repair và trạng thái replica vẫn ảnh hưởng an toàn thu hồi.
- Compaction chưa hoàn tất cũng khiến dung lượng và tombstone tồn tại lâu.

### Cách D — Cân nhắc delete granularity

Nếu mô hình cần xóa “cả tháng dữ liệu của một khách hàng”, xóa hàng triệu row riêng lẻ thường tạo nhiều dấu xóa. Có thể thiết kế **bucket theo retention** để thao tác xóa thuộc phạm vi partition/range hợp lý. Tuy nhiên một partition tombstone có thể che rất nhiều dữ liệu cũ và vẫn phải giữ đủ lâu; nó không phải giấy phép bỏ repair hoặc GC.

Nếu có thể để dữ liệu tự hết hạn theo TTL đồng nhất, hãy kiểm chứng xem đó có giảm chi phí ghi/xóa và cải thiện compaction hơn không. Mỗi lựa chọn cần đo số tombstone bị quét trên **query thực tế**.

## 13. Đường đọc tốt không chỉ là query có `LIMIT`

Các tối ưu nên xem xét cùng nhau:

1. **Đúng partition key:** không quét nhiều token khi không cần.
2. **Đúng clustering range:** chỉ đọc khoảng ngày/giờ/event cần thiết.
3. **Projection cột cần thiết:** tránh `SELECT *` nếu có collection lớn, payload blob hoặc cột không cần gửi về.
4. **Kích thước trang:** driver `fetch size/page size` giúp giới hạn dữ liệu trả về mỗi page, không làm biến mất chi phí tombstone scan.
5. **Giới hạn fan-out:** đọc ba partition ngày có thể hợp lý; đọc hàng nghìn partition để tổng hợp cần thiết kế khác.
6. **Tránh filter không phù hợp khóa:** `ALLOW FILTERING` không thay thế mô hình bảng/query đúng; secondary index/SAI cần đánh giá theo điều kiện và đặc điểm Cassandra.
7. **Đừng đo mỗi p50:** partition lớn, tombstone và replica lệch chậm thường thể hiện ở p95/p99.

Ví dụ query hai chiều:

| Nhu cầu | Thiết kế hợp lý | Tránh |
| --- | --- | --- |
| 20 event gần nhất của khách hàng trong ngày | `(customer_id,event_day)` + clustering time DESC | Một partition `customer_id` chứa 5 năm lịch sử |
| Tags của một event (ít, hữu hạn) | Set nhỏ hoặc `event_tags_by_event` | Set tăng cùng tuổi tài khoản |
| Tìm event theo tag và ngày | `events_by_tag_day` hoặc projection theo query | Quét mọi event rồi kiểm tra collection ở client |
| Xem 7 ngày gần nhất | Truy vấn tối đa 7 bucket ngày và merge có giới hạn | Quét toàn bộ bảng hoặc `IN` cực lớn |
| Giữ event 24 giờ và audit 90 ngày | Tách retention khi phù hợp | Trộn hai TTL trong mọi SSTable của cùng workload |

Đôi khi một partition lớn vẫn là lựa chọn hữu ích khi access pattern bắt buộc và kích thước thực tế có giới hạn; vấn đề là **partition tăng không kiểm soát** và phải scan nhiều hơn lượng thông tin cần trả.

## 14. Java Driver 4.x: đọc theo bucket, giới hạn kết quả

Ứng dụng Java nên làm rõ bucket cần đọc, dùng prepared statement, chọn consistency level và giới hạn kết quả. Ví dụ đọc event của **một ngày**:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public final class CustomerEventReader {
    private final CqlSession session;
    private final PreparedStatement selectByDay;

    public CustomerEventReader(CqlSession session) {
        this.session = session;
        this.selectByDay = session.prepare(
            "SELECT event_time, event_id, event_type, payload " +
            "FROM lab.customer_events_by_day " +
            "WHERE customer_id = ? AND event_day = ? LIMIT ?"
        );
    }

    public List<UUID> recentEventIds(
            UUID customerId, LocalDate eventDay, int maxRows) {

        if (maxRows < 1 || maxRows > 100) {
            throw new IllegalArgumentException("maxRows phải từ 1 đến 100");
        }

        BoundStatement statement = selectByDay.bind(
                customerId, eventDay, maxRows)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(maxRows, 50))
            .setIdempotent(true);

        ResultSet result = session.execute(statement);
        List<UUID> ids = new ArrayList<>();

        for (Row row : result) {
            ids.add(row.getUuid("event_id"));
        }
        return ids;
    }
}
```

Giả định `CqlSession` đã kết nối, `lab` có bảng như bài và RF/datacenter phù hợp `LOCAL_QUORUM`. `LocalDate` đại diện ngày bucket đã chuẩn hóa theo quy tắc nghiệp vụ. Java Driver 4.x dùng codec tương thích cho `date`/`timestamp`; không truyền `String` thay vì `LocalDate` khi statement đã chuẩn bị theo `date`.

`setPageSize` giới hạn số hàng trả về mỗi trang, còn `LIMIT` giới hạn tổng số hàng query. **Cả hai không bảo đảm tombstone scan nhỏ** nếu Cassandra phải duyệt nhiều dữ liệu chết để tìm các hàng còn sống.

### Nếu muốn 20 event mới nhất trong 7 ngày?

Với bảng bucket ngày, ứng dụng có thể đọc các ngày mới nhất theo thứ tự giảm dần, tối đa 20 hàng/ngày và dừng khi đã lấy đủ 20. Cần:

- Thống nhất `event_day` suy ra từ `event_time` và múi giờ (ví dụ UTC).
- Đảm bảo thứ tự trong mỗi partition qua clustering key.
- Xử lý ngày không có dữ liệu và late-arriving events.
- Giới hạn số bucket và timeout của toàn API.
- Khi shard thêm vào partition key, query từng shard và merge toàn cục theo `event_time`/`event_id`; không nối mù kết quả từng shard.

Ví dụ code trên chỉ đọc **một ngày**, không giả vờ tự giải quyết việc merge dữ liệu của nhiều ngày hoặc shard.

## 15. Đo hiệu quả bằng cùng workload và cùng điều kiện

Một thử nghiệm tốt cần kiểm soát:

- Query shape, partition key và phân phối customer nóng/lạnh.
- Dung lượng dữ liệu thực tế, TTL, tỷ lệ update/delete.
- RF, consistency level, datacenter và coordinator routing.
- Tải đọc/ghi đồng thời, compaction, repair và trạng thái cache.
- Thời lượng đo đủ dài để phản ánh p99 và nền compaction.

### Bộ chỉ số trước/sau

| Chỉ số | Trước (bảng không bucket, minh họa) | Sau (bảng bucket, minh họa) |
| --- | ---: | ---: |
| Max partition size | 1,8 GiB | 28 MiB |
| Tombstones scanned p95/query | 8.000 | 150 |
| Read p99 | 480 ms | 85 ms |
| SSTables read/query | Cao, biến động | Ít hơn |
| Queries cần fan-out | Một partition rất rộng | Có thể nhiều bucket khi truy vấn xuyên ngày |
| Ghi bổ sung | Ít projection | Tăng nếu dùng thêm bảng tag/query |

Đây là **số giả định**, không phải kết quả benchmark Cassandra phổ quát. Cần đo cả write amplification, disk/CPU, cache miss và chi phí application merge, không chỉ chọn một dòng p99 tốt nhất.

### Tránh đánh giá sai khi thử

- Bảng mới có ít dữ liệu nên query nhanh hơn; chưa đủ bằng chứng sẽ nhanh khi đầy.
- Query chạy lần thứ hai được OS page cache làm nóng; phải so sánh điều kiện tương đương.
- Chỉ đo một khách hàng bình thường, bỏ qua customer hot.
- Thấy row count nhỏ mà không đo tombstone scanned.
- Ép compaction ở baseline nhưng không ở treatment, hoặc ngược lại.
- Chỉ nhìn latency thành công mà bỏ timeout/error rate.
- Đổi CL từ `QUORUM` sang `ONE` cùng lúc sửa schema rồi kết luận mọi cải thiện đến từ bucketing.

## 16. Quan sát và xử lý sự cố

Dùng lệnh quan sát ở môi trường cho phép:

```bash
nodetool tablestats lab.customer_events_by_day
nodetool tablehistograms lab.customer_events_by_day
nodetool compactionstats
nodetool tpstats
nodetool gcstats
```

Nếu muốn xem đường đi của **một truy vấn**:

```cql
TRACING ON;

SELECT event_time, event_id, event_type, payload
FROM lab.customer_events_by_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND event_day = '2026-11-21'
LIMIT 20;

TRACING OFF;
```

Tracing có overhead; chỉ dùng có kiểm soát ở lab hoặc sampling hợp lý. Trace một lần không mô tả toàn bộ distribution p99; cần ghép với histogram/JMX và OS metrics.

### Kịch bản A — Partition size giảm nhưng p99 không cải thiện

**Kiểm tra:** query có cần đọc nhiều bucket hơn trước không? Driver có fan-out quá rộng không? Có node/replica chậm do GC/I/O? Có phải đang quét nhiều tombstone trong từng bucket?

**Hướng giải quyết:** điều chỉnh bucket theo access pattern, giới hạn số bucket, bảo đảm dữ liệu theo đúng ngày và xem xét cache/compaction.

### Kịch bản B — Collection được tách nhưng chi phí ghi tăng mạnh

**Kiểm tra:** một mutation business tạo bao nhiêu projection write? Có retry gây duplication không? Query mới có cần tất cả projection không? Có tag hot gây partition nóng?

**Hướng giải quyết:** chỉ tạo projection cho query cần phục vụ, thiết kế idempotency/đối soát và chọn bucket/shard cho tag phổ biến.

### Kịch bản C — Tombstone scanned cao dù TTL đã hết lâu

**Kiểm tra:** `gc_grace_seconds`, SSTable overlap, compaction strategy, repair history, snapshot và nhóm TTL trộn ngắn/dài. Một tombstone đủ tuổi không có nghĩa được purge ngay.

**Hướng giải quyết:** ưu tiên mô hình retention và truy vấn trước; đánh giá compaction phù hợp, không ép hạ grace hay xóa SSTable thủ công.

### Kịch bản D — Query LIMIT nhỏ vẫn gây tombstone warning

**Kiểm tra:** partition/range có nhiều row expired không, clustering filter quét lịch sử không, collection updates có sinh dấu xóa nhiều không? Xem query trace và metrics table.

**Hướng giải quyết:** tách dữ liệu nóng/lạnh, bucket và TTL đồng nhất, chỉ truy vấn dải thời gian cần thiết. Không chỉ tăng `tombstone_failure_threshold`.

### Kịch bản E — Một customer làm cả cluster chậm

**Kiểm tra:** token hotspot, tốc độ ghi/đọc của customer đó, phân bố partition size, replica của token, compaction và queue.

**Hướng giải quyết:** nếu bucket ngày chưa đủ, thêm hour/shard với cách hợp nhất dữ liệu đã thiết kế; giới hạn request rate và cân nhắc capacity. Tăng số node **không tự chia một partition đơn lẻ** thành nhiều token nếu partition key không đổi.

## 17. Checklist thiết kế tối ưu

Trước khi triển khai một bảng Cassandra mới, trả lời:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Query nào là đường đọc chính? | `WHERE`, `ORDER BY`, `LIMIT`, dải thời gian và số request |
| Partition key có giới hạn tăng trưởng không? | Event/giây, byte/row, bucket/day/hour/shard, skew p99 |
| Collection có giới hạn số phần tử không? | Cardinality tối đa, kích thước và kiểu update |
| TTL/delete tạo dữ liệu chết như thế nào? | Tần suất mutation, nhóm retention, gc grace và repair |
| Có cần query từ phần tử → event không? | Bảng/projection chuyên biệt và chi phí duy trì |
| Query có phải scan nhiều bucket không? | Fan-out có giới hạn, merge, paging, latency budget |
| Dữ liệu cũ có bị cập nhật/backfill không? | Tác động TWCS, late event, consistency |
| Có đo tombstone scanned không? | Metrics/tracing theo query, p95/p99 và histogram |
| Có kiểm soát lỗi ghi đa bảng không? | Idempotency, retry, reconciliation, source of truth |
| Đã test hot key và dữ liệu đủ lớn chưa? | Benchmark thực, replica load, GC/I/O/compaction |

Không triển khai ngay một schema mới chỉ vì “collection lớn là xấu”: cần đo **mức tăng trưởng, query shape, chi phí ghi và tác động nghiệp vụ**.

## 18. Những hiểu lầm thường gặp

**“`LIMIT 20` thì Cassandra chỉ phải duyệt 20 row.”** Sai. SSTable/tombstone scan có thể lớn hơn rất nhiều.

**“Collection luôn xấu.”** Sai. Collection nhỏ, giới hạn rõ và truy cập nguyên khối/từng phần tử phù hợp vẫn hữu ích.

**“Đổi sang `frozen<map>` sẽ giải quyết mọi collection lớn.”** Sai. Dữ liệu vẫn lớn và thường phải ghi lại cả collection khi sửa.

**“Tách collection thành bảng riêng thì không thể còn partition lớn.”** Sai. Nếu partition key của bảng mới vẫn gom hàng triệu phần tử, bài toán cũ vẫn tồn tại.

**“Thêm clustering key nghĩa là partition đã nhỏ.”** Sai. Clustering key sắp xếp các row **bên trong partition**; chỉ partition key quyết định phân chia token.

**“Thêm shard luôn tốt.”** Sai. Shard giúp phân phối tải nhưng làm query fan-out và merge phức tạp, có thể tăng request.

**“TTL làm dữ liệu biến mất khỏi SSTable ngay khi hết hạn.”** Sai. Dữ liệu hết sống logic trước, compaction/GC mới có thể thu hồi vật lý.

**“Mỗi UPDATE tạo một tombstone giống DELETE.”** Sai. Phải phân biệt phiên bản bị ghi đè với dấu xóa; collection/TTL có hành vi riêng.

**“Tăng tombstone threshold nghĩa là đã tối ưu query.”** Sai. Nó không giảm read amplification.

**“Tombstone scanned / rows returned luôn là tombstone ratio chuẩn.”** Sai. Rows returned không đồng nghĩa live cells scanned.

**“Chạy repair là tombstone tự biến mất.”** Sai. Repair đối soát replica, compaction/GC chịu trách nhiệm xử lý dữ liệu trong SSTable theo điều kiện an toàn.

**“Giảm `gc_grace_seconds` càng thấp càng tốt để dọn đĩa.”** Sai. Replica bỏ lỡ xóa có thể làm dữ liệu cũ sống lại.

**“Thêm nhiều node sẽ tự chia nhỏ một partition nóng.”** Sai. Token của một partition vẫn được xác định từ partition key; cần đổi bucketing/sharding nếu muốn tách tải.

## 19. Câu hỏi và bài tập

1. Vì sao một câu `SELECT ... LIMIT 20` có thể quét hàng nghìn tombstone dù chỉ trả 20 hàng?
2. Một customer có 20 triệu event trong một partition. Thêm clustering column `event_type` có làm nhỏ partition không? Đổi partition key thế nào?
3. Nêu tình huống dùng `map<text,text>` nhỏ là hợp lý và tình huống nên chuyển thành bảng riêng.
4. So sánh update một phần tử của `map` non-frozen với thay một `frozen<map>`.
5. Một sự kiện có 5.000 tag và application cần phân trang tags. Thiết kế `event_tags_by_event` có phù hợp không? Nếu số tag đạt vài triệu thì sao?
6. Có 200 event/giây, khoảng 1 KiB/event. Tính byte theo ngày và giải thích vì sao bucket ngày chưa đủ nếu target partition nhỏ.
7. Nếu chia theo 16 shard/giờ, ứng dụng phải làm gì để trả 20 event mới nhất theo thứ tự toàn cục?
8. Một bảng có TTL 1 ngày và 30 ngày ghi lẫn. Vì sao SSTable không được drop cả tệp sau hai ngày?
9. Vì sao timestamp event đã cũ không đồng nghĩa TTL tính từ timestamp đó?
10. Giải thích `gc_grace_seconds` và repair liên quan nguy cơ dữ liệu zombie như thế nào.
11. Công cụ nào giúp phân tích partition size, tombstone scanned và compaction? Vì sao một ảnh chụp `nodetool` chưa đủ?
12. Bạn có 4.000 tombstone và 100 live cells scanned trong cùng phép đo. Tỷ lệ tham khảo bao nhiêu? Nếu chỉ biết 20 rows returned thì có tính tỷ lệ tương tự được không?
13. Đã bucket theo ngày nhưng một khách hàng vẫn gây hotspot, nêu hai phương án thiết kế kèm đánh đổi.
14. Nếu p99 từ 400 xuống 80 ms sau khi sửa schema nhưng write throughput giảm 40%, đã thành công chưa? Cần đo gì nữa?
15. Vì sao Java Driver `setPageSize(50)` không giải quyết truy vấn phải duyệt quá nhiều tombstone?
16. Khi chuyển từ một bảng sang hai bảng theo access pattern, vì sao cần cơ chế idempotency và reconciliation?

## 20. Tóm tắt quyết định

```text
Query Cassandra chậm / timeout / tombstone warning
                    |
                    v
      Xác định query, partition key, CL, replica
                    |
           +--------+----------+
           |                   |
    Collection lớn?       Partition rất lớn?
           |                   |
    Có tăng vô hạn?      Có bucket/time key?
           |                   |
    Chuyển thành bảng   Chia ngày/giờ/shard
    theo query khi cần  và giới hạn fan-out
           |                   |
           +--------+----------+
                    |
              Tombstone nhiều?
                    |
        Xác định DELETE, TTL, null,
        collection update, data cũ
                    |
        Tối ưu retention + query range
        + compaction phù hợp + repair an toàn
                    |
                    v
        Đo p95/p99 + tombstone scanned
        + partition size + write/disk cost
```

**Ghi nhớ:** Collection nên **nhỏ và có giới hạn**, partition key phải giữ **số row/byte trong một phạm vi dự báo được**, và tombstone cần được quản lý từ **mô hình dữ liệu, TTL/delete pattern tới compaction/repair**. Để giảm p99, tối ưu số cell/SSTable thực sự phải quét — **không chỉ số hàng được trả về**. Luôn cân bằng giảm read amplification với fan-out, write amplification và độ phức tạp duy trì bảng phụ của ứng dụng Java.
