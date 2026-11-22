# Cardinality khóa, dữ liệu lệch và điểm nóng

Trong Apache Cassandra, **partition key** quyết định một hàng thuộc phân vùng logic nào và tập replica nào chịu trách nhiệm lưu dữ liệu. Khi thiết kế bảng wide-column, chỉ chọn một khóa “có nhiều giá trị” là chưa đủ: cần biết **các giá trị phân bố ra sao**, **mỗi giá trị tích lũy bao nhiêu dữ liệu** và **mỗi giá trị nhận bao nhiêu lượt đọc/ghi**. Ba yếu tố này quyết định liệu workload có được trải đều trên cluster hay dồn vào một vài phân vùng và node.

**Cardinality** mô tả số giá trị partition key phân biệt. **Skew (dữ liệu lệch)** xảy ra khi dữ liệu hoặc lưu lượng phân bố không đều giữa các giá trị. **Hot partition** là một phân vùng nhận tải quá tập trung; **hot node** là node chịu tải cao bất thường so với các node khác. Các khái niệm liên quan nhưng không thay thế cho nhau.

Bài học thuộc chương **Khóa và phân vùng** của module Apache Cassandra. Hiểu chúng giúp thiết kế bảng theo truy vấn, dự kiến cách replication và consistency tác động đến tải, phát hiện lỗi hiệu năng, và xây dựng đường đọc/ghi an toàn từ ứng dụng Java.

Sau bài học, bạn có thể:

- Tính và diễn giải cardinality của partition key đơn hoặc ghép.
- Phân biệt **lệch dung lượng**, **lệch số hàng** và **lệch tần suất truy cập**.
- Giải thích vì sao hashing/token không tự cân bằng workload có các khóa “nóng”.
- Nhận ra những thiết kế gây hot partition, large partition và fan-out query.
- Chọn time bucket, khóa ghép hoặc shard có kiểm soát theo yêu cầu truy vấn.
- Sử dụng CQL, metrics và Java Driver để kiểm tra, giảm điểm nóng và xử lý retry.

## 1. Cardinality của partition key là gì?

**Cardinality của partition key** là số **giá trị khóa phân vùng phân biệt** xuất hiện trong dữ liệu tại thời điểm hoặc giai đoạn đang xét.

Ví dụ một bảng có partition key `tenant_id` với bốn tenant đã ghi dữ liệu:

```text
tenant_id = acme
tenant_id = beta
tenant_id = gamma
tenant_id = delta

Cardinality(partition key) = 4
```

Nếu bảng có partition key ghép `(tenant_id, device_id)` thì cardinality là **số cặp phân biệt**, không phải số tenant cộng số thiết bị:

```text
('acme', D1)
('acme', D2)
('beta', D1)
('beta', D3)
('gamma', D7)

Cardinality((tenant_id, device_id)) = 5
```

Hai thiết bị đều mang giá trị `D1` nhưng thuộc tenant khác nhau nên tạo **hai partition keys**. Ngược lại, hàng nghìn sự kiện có cùng `('acme', D1)` vẫn chỉ tạo **một giá trị partition key**.

| Khóa | Cardinality có thể có | Nguy cơ chính |
| --- | --- | --- |
| `status` với các giá trị `NEW`, `PAID`, `CANCELLED` | Rất thấp: tối đa vài giá trị | Nhiều hàng/ghi dồn về ít phân vùng. |
| `tenant_id` | Bằng số tenant đang có dữ liệu | Tenant lớn có thể áp đảo tenant nhỏ. |
| `(tenant_id, user_id)` | Bằng số cặp tenant–user phân biệt | Thường phân tán hơn, nhưng user cực nóng vẫn tạo hotspot. |
| `(tenant_id, device_id, event_day)` | Bằng số tổ hợp tenant–device–ngày | Giới hạn lịch sử theo ngày; ngày hiện tại có thể vẫn nóng. |
| `event_id` duy nhất cho mỗi sự kiện | Rất cao, gần bằng số sự kiện | Phân phối nhiều phân vùng nhỏ nhưng khó đọc timeline theo thực thể. |

**Cardinality cao không đồng nghĩa mô hình tốt.** Nếu mỗi sự kiện trở thành một phân vùng riêng, các truy vấn như “100 sự kiện mới nhất của thiết bị” phải tìm, ghép nhiều phân vùng. Ngược lại, khóa có cardinality thấp có thể hợp lý nếu dữ liệu ít và mọi truy vấn đều chọn đúng một giá trị nhỏ.

### Cardinality của partition key khác cardinality của clustering column

Xét bảng:

```sql
CREATE TABLE actions_by_status (
    status text,
    happened_at timestamp,
    action_id uuid,
    payload text,
    PRIMARY KEY (status, happened_at, action_id)
);
```

Dù `action_id` hầu như không trùng và `happened_at` có rất nhiều giá trị, **chỉ `status` là partition key**. Hàng triệu `action_id` khác nhau không làm cardinality của partition key tăng. Chúng chỉ tạo nhiều clustering rows trong mỗi phân vùng `status`.

Muốn partition key ghép hai cột, cú pháp phải có cặp ngoặc bên trong, chẳng hạn `PRIMARY KEY ((tenant_id, user_id), happened_at, action_id)`.

## 2. Cardinality cao vẫn có thể tạo dữ liệu lệch

Cassandra thường dùng `Murmur3Partitioner` để ánh xạ **toàn bộ partition key** sang token. Token được phân bố trên ring; chiến lược replication xác định các node giữ bản sao. Hashing giúp phân tán **các khóa khác nhau** theo token, nhưng không chia một **giá trị partition key duy nhất** thành nhiều phần đặt trên các nhóm replica độc lập.

Giả sử một hệ thống có 100 tenant. Trong một phút:

- Tenant `whale` gửi **12.000 ghi/giây**.
- 99 tenant còn lại gửi tổng cộng **12.000 ghi/giây**.
- Bảng chỉ dùng `tenant_id` làm partition key.

Tenant `whale` chiếm **1% số giá trị khóa** nhưng tạo **50% tổng số ghi**. Nếu mỗi lượt ghi chứa một clustering key khác nhau, chúng đều đi vào **cùng một phân vùng logic** của tenant này.

```text
100 partition keys
│
├── whale             : 12.000 write/s  (50% tổng ghi)
├── tenant-002 ...    : khoảng 121 write/s mỗi tenant nếu chia đều
├── tenant-003 ...
└── tenant-100 ...

Murmur3 phân bố token, nhưng không chia riêng
partition 'whale' thành 12.000 partition keys.
```

Tăng số node có thể giúp cluster chứa nhiều partition keys hơn, nhưng không bảo đảm xử lý ổn định một khóa riêng lẻ đang quá nóng. Tương tự, tăng replication factor thêm bản sao của cùng phân vùng chứ không phân tán nó thành các phân vùng nhỏ hơn.

### Ba dạng skew thường gặp

| Dạng lệch | Dấu hiệu | Hậu quả |
| --- | --- | --- |
| **Data/size skew** | Một số khóa có nhiều hàng hoặc nhiều byte hơn hẳn | Large partition, compaction và repair/streaming tốn tài nguyên. |
| **Write skew** | Một số khóa nhận phần lớn INSERT/UPDATE/DELETE | Replica phụ trách khóa bị dồn CPU, I/O, hàng đợi và ghi SSTable. |
| **Read skew** | Một số khóa nhận nhiều SELECT hoặc truy vấn khoảng rộng | Độ trễ cao, áp lực cache/memtable/SSTable và mạng trên các replica liên quan. |

Một partition có thể lớn nhưng ít truy cập; hoặc rất nhỏ nhưng nhận hàng chục nghìn truy vấn/giây. Vì vậy phải đo **dung lượng và lưu lượng độc lập**.

## 3. Phân biệt hot partition và hot node

**Hot partition** gắn với **một giá trị partition key** nhận tải lớn hoặc vượt ngân sách tài nguyên cho mỗi khóa. **Hot node** gắn với **máy chủ** chịu nhiều tải hơn mức nó có thể xử lý.

```text
                           replication factor = 3
Hot key P ── token(P) ───> Replica A
                       ├> Replica B
                       └> Replica C
                               
Các request cho P vẫn tập trung vào tập replica của P.
```

Hot node có thể do:

1. Một hot partition trên node đó.
2. Nhiều partition keys “vừa nóng” cùng được ánh xạ tới các token range/replica sets liên quan.
3. Replica placement và phân bố token/ring chưa phù hợp với khối lượng dữ liệu.
4. Coordinator, mạng, I/O, GC, compaction hoặc giới hạn tài nguyên của node.

Đừng nhìn một node CPU cao rồi kết luận ngay partition key bị lệch. Cần đối chiếu key/bảng/truy vấn với CPU, I/O, p95/p99 latency, pending compactions và topology.

### Replication và consistency tác động ra sao?

Với `replication factor = 3`, một ghi thông thường cần được gửi tới các replica chịu trách nhiệm cho partition key. `consistency level` quy định số xác nhận cần thiết để thao tác được báo thành công; nó **không thay đổi khóa phân vùng** và không bảo đảm các replica khác không có công việc liên quan.

- Tăng `RF` có thể tăng khả năng chịu lỗi và tạo thêm lựa chọn cho read routing tùy topology, nhưng làm tăng tổng số bản sao và không chia một hot partition thành nhiều partition khác nhau.
- Chọn `LOCAL_ONE`, `LOCAL_QUORUM` hay mức khác ảnh hưởng đánh đổi tính nhất quán/độ trễ/số xác nhận; đây không phải giải pháp thay thế thiết kế partition key.
- Sự kiện read/write tập trung ở một khóa vẫn cần được đo trên các replica và coordinator liên quan, thay vì chỉ quan sát mức sử dụng trung bình toàn cluster.

## 4. Những thiết kế khóa dễ gây điểm nóng

### 4.1. Partition key chỉ là trạng thái ít giá trị

```sql
CREATE TABLE jobs_by_status (
    status text,
    created_at timestamp,
    job_id uuid,
    payload text,
    PRIMARY KEY (status, created_at, job_id)
);
```

Nếu `status` chỉ có `PENDING`, `RUNNING` và `DONE`, toàn bộ job nằm trong tối đa ba phân vùng logic. `created_at` và `job_id` là clustering columns; số lượng lớn của chúng không tạo thêm partition keys.

Điều này dễ gây phân vùng rất lớn và tập trung đọc/ghi khi `PENDING` chứa phần lớn công việc.

### 4.2. Partition key chỉ là tenant

```sql
CREATE TABLE events_by_tenant (
    tenant_id text,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (tenant_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Nếu mỗi tenant có rất ít sự kiện, mô hình có thể phục vụ “timeline một tenant”. Nhưng tenant đông người dùng hoặc phát nhiều sự kiện sẽ dồn vào một phân vùng. Không nên giả định 10.000 tenant đồng nghĩa 10.000 phân vùng có lượng việc tương đương nhau.

### 4.3. Partition key ghép nhưng một thành phần ít phân tán

```sql
-- Dữ liệu chia theo tenant và ngày:
PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
```

Bucket ngày giúp giới hạn lịch sử trong mỗi phân vùng, nhưng mọi sự kiện của tenant `whale` **trong ngày hiện tại** vẫn ghi chung một partition key. Số partition keys tăng theo thời gian **không làm giảm write hotspot ngay trong ngày**.

### 4.4. Partition key là timestamp hoặc event ID duy nhất

```sql
-- Mỗi sự kiện gần như một partition key:
PRIMARY KEY ((tenant_id, event_id), occurred_at)
```

Cách này có cardinality cao và có thể phân bố ghi tốt nếu ID phân tán đều. Nhưng truy vấn “sự kiện mới nhất của tenant T trong một giờ” sẽ không còn một partition lookup đơn giản. Khi đọc theo dải thời gian, phải có đường truy cập bổ sung hoặc tập hợp nhiều khóa.

**Nguyên tắc thiết kế theo truy vấn:** không “chữa hotspot” chỉ bằng cách nhét khóa ngẫu nhiên vào partition key mà chưa có cách định tuyến và đọc dữ liệu.

## 5. Phân tích một tình huống theo dữ liệu và tải

Một hệ thống thu thập event từ thiết bị có các yêu cầu:

1. Lấy các event mới nhất của **một thiết bị** trong **một giờ**.
2. Lấy timeline sự kiện của **toàn tenant** trong một khoảng ngắn.
3. Ghi chịu được tenant lớn, có thiết bị phát sự kiện dày đặc.
4. Dữ liệu cần được giữ theo TTL và có thể đọc qua nhiều ngày.

Từ yêu cầu này, có thể thiết kế **nhiều bảng theo kiểu truy vấn**, không cố dùng một bảng với một khóa cho mọi mục tiêu.

| Bảng phục vụ truy vấn | Partition key gợi ý | Clustering columns | Điểm đánh đổi |
| --- | --- | --- | --- |
| Lịch sử của thiết bị trong giờ | `(tenant_id, device_id, hour_bucket)` | `occurred_at`, `event_id` | Thiết bị cực nóng có thể cần bucket nhỏ hơn. |
| Timeline toàn tenant trong phút | `(tenant_id, minute_bucket, shard_id)` | `occurred_at`, `event_id` | Đọc phải fan-out sang các shard, hợp nhất theo thời gian. |
| Tra cứu một event theo ID | `(tenant_id, event_id)` | Có thể không cần | Không đáp ứng trực tiếp timeline theo thời gian. |

Đa bảng có thể tạo **dữ liệu được lưu lặp**. Để bảo đảm các bản sao nghiệp vụ được cập nhật đúng, ứng dụng cần có quy tắc ghi, retry, backfill và đối chiếu; ghi nhiều bảng không tự trở thành transaction nguyên tử xuyên bảng/phân vùng.

## 6. Giảm kích thước bằng time bucketing

Nếu dữ liệu tăng theo thời gian, hãy đưa thành phần bucket vào partition key:

```sql
CREATE TABLE events_by_device_hour (
    tenant_id   text,
    device_id   uuid,
    hour_bucket timestamp,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

**Quy ước:** `hour_bucket` là đầu giờ UTC của `occurred_at`, ví dụ sự kiện `2026-11-21T08:13:20Z` có `hour_bucket = 2026-11-21T08:00:00Z`.

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND occurred_at >= '2026-11-21T08:10:00Z'
  AND occurred_at <  '2026-11-21T08:20:00Z'
LIMIT 100;
```

Cassandra được cung cấp đủ partition key và một đoạn clustering key. Đây là đường truy cập phù hợp cho lịch sử của một thiết bị trong một giờ.

Nếu thiết bị nhận **2.000 ghi/giây liên tục trong giờ hiện tại**, toàn bộ 2.000 ghi/giây vẫn thuộc **một partition key**; bucket giờ chỉ ngăn dữ liệu nhiều giờ dồn mãi vào một phân vùng. Trong trường hợp này, cần bucket nhỏ hơn và/hoặc shard có kiểm soát.

### Bucket phải khớp quy mô lưu lượng và kiểu đọc

| Chiều bucket | Lợi ích | Chi phí |
| --- | --- | --- |
| Ngày | Ít phân vùng phải đọc cho lịch sử nhiều ngày | Mỗi phân vùng có thể chứa nhiều dữ liệu và ghi nóng trong một ngày. |
| Giờ | Giới hạn mỗi phân vùng theo giờ | Truy vấn nhiều ngày phải đọc nhiều bucket. |
| Phút | Giảm kích thước và thời gian một khóa nhận ghi | Truy vấn lịch sử dài có thể cần hàng nghìn bucket. |

Bucket theo ngày/giờ/phút không tự “đúng” cho mọi hệ thống. Quyết định phải dựa trên **tải cao điểm**, **byte trung bình mỗi sự kiện**, **truy vấn thường xuyên**, **ngân sách độ trễ** và khả năng của replica.

## 7. Giảm write hotspot bằng shard có kiểm soát

Khi tenant cần ghi rất nhiều sự kiện **ngay trong một bucket hiện tại**, có thể thêm `shard_id` vào partition key để tạo nhiều phân vùng có thể phân tán theo token.

Ví dụ bảng timeline **toàn tenant theo phút**, chia theo 12 shard:

```sql
CREATE TABLE tenant_events_by_shard_minute (
    tenant_id     text,
    minute_bucket timestamp,
    shard_id      smallint,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, minute_bucket, shard_id),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Một cách chọn shard ổn định là dùng hash từ ID sự kiện đã được tạo **một lần cho nghiệp vụ**, rồi lấy phần dư theo số shard:

```text
shard_id = floorMod(stableHash(event_id), 12)

Partition key =
    (tenant_id, minute_bucket, shard_id)

Ví dụ:
  ('whale', 2026-11-21T08:30Z, 0)
  ('whale', 2026-11-21T08:30Z, 1)
  ...
  ('whale', 2026-11-21T08:30Z, 11)
```

Nếu tổng lưu lượng ghi vào tenant này là **12.000 ghi/giây** và sự kiện phân tán **gần đều** giữa 12 shard, mục tiêu trung bình là khoảng **1.000 ghi/giây/partition key** trong phút đang hoạt động. Đây chỉ là ước lượng lý tưởng: tải từng shard có thể lệch, token có thể đặt các shard trên một số node/replica trùng nhau và 1.000 ghi/giây vẫn có thể là điểm nóng cần đo thực tế.

Với giả định mỗi event mang **500 byte payload logic**:

```text
Số hàng mỗi shard/phút
  ≈ 12.000 × 60 / 12 = 60.000 hàng

Payload logic mỗi shard/phút
  ≈ 60.000 × 500 B
  = 30.000.000 B ≈ 28,6 MiB
```

Số liệu trên chưa gồm clustering keys, metadata, nén, tombstone và chi phí replica.

### Ví dụ ghi CQL vào một shard

```sql
INSERT INTO tenant_events_by_shard_minute (
    tenant_id, minute_bucket, shard_id,
    occurred_at, event_id, event_type, payload
) VALUES (
    'whale',
    '2026-11-21T08:30:00Z',
    7,
    '2026-11-21T08:30:15Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'purchase',
    '{"total":120}'
);
```

Ở đây `7` là shard **minh họa**. Trong ứng dụng, `shard_id` phải được tính nhất quán từ thuật toán đã chốt; không tự thay đổi shard giữa các lần retry.

### Đọc một shard

```sql
SELECT occurred_at, event_id, event_type, payload
FROM tenant_events_by_shard_minute
WHERE tenant_id = 'whale'
  AND minute_bucket = '2026-11-21T08:30:00Z'
  AND shard_id = 7
  AND occurred_at >= '2026-11-21T08:30:00Z'
  AND occurred_at <  '2026-11-21T08:31:00Z'
LIMIT 100;
```

Để trả **100 event mới nhất của toàn tenant trong phút**, ứng dụng phải đọc các shard `0` đến `11`, rồi **merge theo `occurred_at DESC, event_id ASC`** và lấy 100 hàng đầu tiên. Một truy vấn vào `shard_id = 7` không đại diện cho toàn tenant.

Lưu ý khi triển khai:

- Giới hạn số truy vấn shard chạy đồng thời; fan-out quá lớn có thể chuyển hotspot đọc sang coordinator/ứng dụng.
- Đồng bộ **số lượng shard, hàm hash, cách tính bucket** giữa mọi producer và reader.
- Nếu đổi số shard từ 12 lên 24, dữ liệu lịch sử **không tự phân bố lại**. Cần chiến lược versioning, thời điểm chuyển đổi, đọc song song cấu hình cũ/mới hoặc migration.
- Với request đọc “một event theo ID” cần biết shard theo ID **và** bucket, hoặc có bảng tra cứu ID; nếu chỉ biết ID mà không biết minute bucket, truy vấn timeline không xác định được partition key.
- Không giả định mỗi shard nằm trên một node riêng. Token placement và replica sets cần được xác minh bằng metrics thực tế.

## 8. Khi thêm khóa ghép lại làm truy vấn không phù hợp

Nhiều người thấy `(tenant_id, user_id, event_day)` có cardinality lớn hơn `tenant_id` và cho rằng mọi truy vấn sẽ nhanh hơn. Nhưng CQL muốn chọn đúng partition key cần **đủ các thành phần**:

```sql
CREATE TABLE user_events_by_day (
    tenant_id   text,
    user_id     uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, user_id, event_day),
        occurred_at,
        event_id
    )
);
```

Truy vấn phù hợp:

```sql
SELECT occurred_at, event_id, payload
FROM user_events_by_day
WHERE tenant_id = 'acme'
  AND user_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND event_day = '2026-11-21'
LIMIT 50;
```

Truy vấn **không xác định partition key đầy đủ**:

```sql
-- Chỉ biết tenant, thiếu user_id và event_day:
SELECT *
FROM user_events_by_day
WHERE tenant_id = 'acme';
```

Không có chỉ mục hoặc cấu trúc hỗ trợ phù hợp, Cassandra thường từ chối truy vấn rộng này; `ALLOW FILTERING` có thể cho phép một số trường hợp nhưng có nguy cơ quét lớn. Muốn lấy timeline toàn tenant, cần một bảng truy vấn khác như `tenant_events_by_shard_minute` hoặc chiến lược tổng hợp riêng.

**Tăng cardinality giúp phân bố khóa, nhưng cũng có thể tăng chi phí truy vấn đa khóa.** Phải đánh đổi số partition đọc, độ lớn mỗi partition và số replica chịu tải.

## 9. Đọc phân bố dữ liệu và điểm nóng từ metrics

Không nên suy luận skew chỉ từ số row trong một kết quả `SELECT LIMIT 20`. Cassandra có thể chứa hàng triệu row trong phân vùng ấy, và việc chỉ đọc 20 row không nói lên tổng số byte.

### Những số liệu cần theo dõi

| Nhóm số liệu | Gợi ý phát hiện |
| --- | --- |
| **Partition size histogram / maximum** | Một số phân vùng chiếm nhiều byte hơn phần còn lại. |
| **Cell count histogram** | Một số phân vùng có rất nhiều cell/clustering rows. |
| **Read/write latency p95, p99; timeout** | Workload bị chậm hoặc có đuôi độ trễ cao. |
| **Per-table read/write volume** | Xác định bảng gây tải trước khi đi xuống partition keys. |
| **Top key / phân tích request theo partition key** | Một số partition keys tạo tỷ trọng request bất thường. |
| **CPU, disk I/O, GC, network theo node** | Kiểm tra hotspot ở tầng replica/coordinator. |
| **SSTables per read, tombstones scanned** | Phân biệt dữ liệu lớn với read amplification do SSTable/tombstone. |
| **Pending compactions, streaming/repair load** | Công việc nền có thể tạo hoặc khuếch đại chậm đọc/ghi. |

Tùy phiên bản Cassandra, có thể bắt đầu với:

```bash
nodetool tablestats my_keyspace.tenant_events_by_shard_minute
nodetool tablehistograms my_keyspace tenant_events_by_shard_minute
```

Kết quả phụ thuộc phiên bản và nút đang truy vấn; histogram/statistics không phải số đo chính xác tức thời của **từng** partition sống. Một số bản Cassandra có lệnh hoặc cơ chế sampling theo các partition keys được đọc/ghi nhiều (chẳng hạn `nodetool toppartitions`); cú pháp và khả năng sẵn có cần tra theo phiên bản đang chạy.

Khi cần chẩn đoán đỉnh tải theo khóa, ứng dụng có thể ghi metrics **không chứa thông tin nhạy cảm** theo bucket hoặc nhóm key đã chuẩn hóa. Tránh đưa toàn bộ ID người dùng làm nhãn metric cardinality cao trong hệ thống giám sát: chính metrics cũng có thể bị quá tải. Có thể dùng sampling, heavy-hitter tracking, hash rút gọn hoặc tổng hợp theo tenant/shard, rồi điều tra chọn lọc.

### Quy trình chẩn đoán có thể lặp lại

1. Xác nhận **symptom**: chậm ở bảng/truy vấn nào, thời gian nào, tỷ lệ timeout bao nhiêu.
2. Kiểm tra **độ lệch node**: chỉ vài replica hoặc coordinator bị CPU/I/O/mạng cao?
3. Kiểm tra **kích thước và cell**: có large partition hoặc phần đuôi dữ liệu bất thường?
4. Kiểm tra **độ lệch truy cập**: partition keys nào chiếm nhiều lượt đọc/ghi nhất?
5. Đối chiếu **schema và `WHERE`**: truy vấn có đủ partition key, khoảng clustering đúng và `LIMIT`/paging phù hợp?
6. Xem **TTL, tombstone, compaction, repair** để loại trừ nguyên nhân phụ hoặc kết hợp.
7. Thử nghiệm **bucket/shard mới** trên workload đại diện và so p95/p99, tải replica, số phân vùng đọc và chi phí lưu trữ.

**Đừng dùng `SELECT COUNT(*)` cho mọi phân vùng lớn để đo skew trên production.** Đếm dữ liệu bằng truy vấn có thể tạo thêm tải nặng; ưu tiên metric, histograms, luồng ghi và sampling có kiểm soát.

## 10. Quy tắc chọn partition key cân bằng tải và hiệu năng đọc

Một thiết kế tốt không chỉ tối đa cardinality. Hãy đánh giá theo bốn câu hỏi:

1. **Query:** ứng dụng cần biết những giá trị nào để xác định một partition key? Có hay truy vấn “toàn tenant” hay chỉ “một user/thiết bị”?
2. **Size:** trong khoảng lưu trữ, một phân vùng dự kiến có bao nhiêu hàng/cell/byte ở tải trung bình và **đỉnh**?
3. **Frequency:** một khóa đơn lẻ có thể nhận bao nhiêu request/giây? Giá trị lớn nhất lệch bao nhiêu so với trung vị?
4. **Fan-out:** sau khi thêm bucket hoặc shard, một truy vấn nghiệp vụ phải đọc bao nhiêu phân vùng và có phải merge kết quả không?

| Dấu hiệu | Thiết kế có thể cần thay đổi |
| --- | --- |
| Rất ít partition key, mỗi key nhiều hàng | Thêm thực thể hoặc bucket vào partition key nếu khớp truy vấn. |
| Nhiều partition key nhưng một số key quá nóng | Chia shard có kiểm soát, giảm tải hoặc thay đường ghi; kiểm tra đọc fan-out. |
| Dữ liệu tăng mãi theo thời gian | Time bucketing, TTL và vòng đời dữ liệu. |
| Mỗi event một phân vùng, truy vấn timeline phải đọc nhiều khóa | Gom theo thực thể/bucket và sắp bằng clustering columns. |
| Nhiều query thiếu thành phần partition key | Thiết kế bảng theo truy vấn khác hoặc chỉ mục phù hợp, không dựa vào lọc rộng. |
| Bucket ngày vẫn quá nóng trong giờ cao điểm | Bucket giờ/phút, shard và/hoặc giới hạn tốc độ; đo tải replica. |

Với dữ liệu time-series có TTL, có thể đánh giá `TimeWindowCompactionStrategy` trên các phiên bản và pattern ghi phù hợp. Compaction và repair **không thay đổi partition key**, nên đây là bước tối ưu lưu trữ và vận hành, không phải cách tự chia một hot partition.

## 11. Ghi shard ổn định từ ứng dụng Java

Ví dụ dưới đây dùng **Java Driver 4.x**, giả định `CqlSession` đã kết nối tới keyspace có bảng `tenant_events_by_shard_minute`. Ứng dụng chọn 12 shard dựa trên `eventId` được tạo **một lần trước khi gửi**. Cùng một event khi retry phải giữ nguyên `eventId` và `occurredAt`.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class TenantEventWriter {
    private static final int SHARD_COUNT = 12;

    private final CqlSession session;
    private final PreparedStatement insert;

    public TenantEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO tenant_events_by_shard_minute " +
            "(tenant_id, minute_bucket, shard_id, occurred_at, " +
            "event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public void writeEvent(
            String tenantId,
            Instant occurredAt,
            UUID eventId,
            String eventType,
            String payload) {

        Instant bucket = occurredAt.truncatedTo(ChronoUnit.MINUTES);
        short shardId = (short) Math.floorMod(eventId.hashCode(), SHARD_COUNT);

        session.execute(insert.bind(
            tenantId, bucket, shardId, occurredAt,
            eventId, eventType, payload
        ));
    }
}
```

Trong ví dụ này, `eventId.hashCode()` là một hàm băm **xác định** của UUID trong Java, được đưa về khoảng `0..11` bằng `floorMod`. Nó chỉ phục vụ minh họa thuật toán phân shard giữa các dịch vụ Java cùng quy ước; nếu hệ thống đa ngôn ngữ, hãy định nghĩa thuật toán hash trên byte và phiên bản rõ ràng để mọi producer/consumer cho cùng kết quả.

Các nguyên tắc vận hành:

- Cố định thuật toán hash và `SHARD_COUNT` cho dữ liệu đã ghi. Nếu đổi, cần biết **quy tắc cũ** khi đọc dữ liệu lịch sử hoặc migration.
- Nếu cùng sự kiện được retry với ID mới, timestamp mới hoặc bucket mới, dữ liệu có thể được ghi ở partition khác và tạo bản ghi trùng logic.
- Cassandra `INSERT` thông thường có semantics **upsert** theo **toàn bộ primary key**. Tính ổn định của shard **và** clustering columns mới giúp retry về đúng một hàng.
- Ghi vào một bảng timeline không tự tạo giao dịch nguyên tử với bảng tra cứu/số liệu tổng hợp khác. Cần xử lý các trường hợp partial failure.
- Java Driver có thể tận dụng routing key từ prepared statement khi được bind đủ partition key; theo dõi load balancing, timeout, consistency và backpressure thay vì tăng concurrency vô hạn.

### Đọc timeline toàn tenant trong một phút

```text
Tính minute_bucket từ thời điểm yêu cầu
              |
              v
Đọc shard 0..11 (concurrency có giới hạn)
              |
              v
Mỗi shard trả kết quả theo occurred_at DESC, event_id ASC
              |
              v
Merge 12 luồng theo cùng comparator
              |
              v
Chọn 100 event mới nhất toàn tenant
```

Nếu phải trả **top 100 toàn cục**, việc lấy tối đa 100 hàng đầu tiên **ở mỗi shard** là đủ để không bỏ sót một hàng thuộc top 100, với điều kiện cùng comparator và các query phủ đúng khoảng thời gian. Tuy nhiên, cách này có thể đọc tới 1.200 hàng, nên trong hệ thống thực có thể dùng merge theo trang, tiếp tục fetch khi cần và giới hạn số query song song.

Đừng áp dụng `ORDER BY` với kỳ vọng Cassandra tự sắp xếp toàn cục giữa 12 partition keys. Thứ tự clustering chỉ có hiệu lực trong mỗi phân vùng.

## 12. Tình huống thực hành

Một dịch vụ thương mại điện tử có 500 cửa hàng. Bảng ban đầu dùng:

```sql
CREATE TABLE sales_by_store (
    store_id uuid,
    sold_at timestamp,
    sale_id uuid,
    amount decimal,
    PRIMARY KEY (store_id, sold_at, sale_id)
);
```

Trong giờ cao điểm:

- 499 cửa hàng nhỏ có trung bình **2 giao dịch/giây/cửa hàng**.
- Một cửa hàng lớn có **5.000 giao dịch/giây**.
- Payload logic mỗi giao dịch giả định **400 byte**.
- Mục tiêu đọc chính: “50 giao dịch mới nhất của một cửa hàng”.
- Mục tiêu đọc phụ: “mọi giao dịch trong 15 phút đã chọn của cửa hàng”.

**Câu hỏi:**

1. Cardinality partition key của bảng hiện tại là bao nhiêu, giả sử cả 500 cửa hàng đều có dữ liệu?
2. Tổng tốc độ ghi gần đúng là bao nhiêu? Cửa hàng lớn chiếm bao nhiêu phần trăm?
3. Token hashing có tự chia 5.000 giao dịch/giây của cửa hàng lớn ra nhiều partition keys không?
4. Nếu giữ một partition key cho mỗi cửa hàng, sau 1 giờ cửa hàng lớn có bao nhiêu hàng và bao nhiêu payload logic?
5. Thêm bucket giờ có làm giảm **write hotspot trong giờ hiện tại** không?
6. Giả sử thêm 10 shard và phân phối lý tưởng, mỗi shard nhận khoảng bao nhiêu ghi/giây?
7. Câu “50 giao dịch mới nhất” cần thay đổi như thế nào nếu các giao dịch được chia đều sang 10 shard?
8. Những metrics nào cần quan sát để chứng minh phương án shard thực sự tốt hơn?

**Đáp án có giải thích:**

1. **500 partition keys**, vì `store_id` là partition key đơn.
2. Tổng `499 × 2 + 5.000 = 5.998 ghi/giây`; cửa hàng lớn chiếm khoảng **83,4%**.
3. **Không.** Mọi sự kiện cùng `store_id` vào một phân vùng logic và cùng tập replica, bất kể có nhiều clustering keys.
4. `5.000 × 3.600 = 18.000.000 hàng`; payload `18.000.000 × 400 = 7.200.000.000 byte ≈ 6,71 GiB`, chưa tính overhead, compaction, nén và replica.
5. **Chưa chắc giảm tải hiện tại.** Bucket giờ chỉ tách các giờ khác nhau; các bản ghi của **cùng giờ** vẫn vào một phân vùng.
6. Lý tưởng **500 ghi/giây/shard**; tải thực có thể lệch và replica sets có thể trùng.
7. Đọc các shard của bucket thích hợp, hợp nhất kết quả theo thời gian và ID, lấy top 50; cần xử lý cả bucket trước đó nếu trang đầu không đủ 50 bản ghi.
8. Partition size/cell histogram, top keys và phân phối ghi theo shard, p95/p99 latency, timeout, CPU/I/O, compaction backlog và chi phí fan-out đọc.

Bài tập cho thấy tăng cardinality từ 500 lên nhiều partition keys theo bucket và shard **chỉ có ích khi workload thực sự được phân bố tốt** và các đường truy vấn quan trọng vẫn được phục vụ với chi phí chấp nhận được.

## 13. Checklist thiết kế và vận hành

Khi thấy dữ liệu lệch hoặc có điểm nóng, hãy tự kiểm tra:

1. **Khóa nào** là partition key thực sự? Đọc đúng dấu ngoặc trong `PRIMARY KEY`.
2. Cardinality đang đo ở **mức tenant, thiết bị, user, bucket, shard** hay toàn tổ hợp partition key?
3. Phân bố số hàng/byte và lưu lượng **trên từng key** có bị lệch mạnh, đặc biệt ở p95/p99/max không?
4. Những key lớn có đồng thời là key nóng không, hay cần xử lý hai nhóm sự cố khác nhau?
5. Thêm bucket hoặc shard sẽ làm **mỗi truy vấn đọc bao nhiêu phân vùng**, cần merge ra sao?
6. Ứng dụng có giữ **ID, bucket và shard ổn định khi retry** không?
7. Mức replication/consistency, topology và giới hạn của node có phù hợp tải và mục tiêu độ trễ?
8. Số liệu trước/sau thay đổi có chứng minh giảm tải trên replica và cải thiện p95/p99, không chỉ giảm kích thước trung bình không?

**Ghi nhớ:** cardinality cao cung cấp **nhiều khóa để phân phối**, nhưng hashing chỉ quyết định vị trí của từng khóa. Tính cân bằng thực tế phụ thuộc **lưu lượng và lượng dữ liệu trên các khóa**. Một mô hình Cassandra tốt phải cân bằng cách chia dữ liệu, chi phí đọc theo truy vấn, chiến lược replication và khả năng vận hành compaction/repair, đồng thời cho phép ứng dụng Java ghi và thử lại một cách nhất quán.

