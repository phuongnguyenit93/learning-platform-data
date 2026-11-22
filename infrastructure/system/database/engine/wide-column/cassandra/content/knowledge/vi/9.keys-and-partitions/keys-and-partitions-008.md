# Phân vùng lớn, hàng rộng và ảnh hưởng đến đọc/ghi

Trong Apache Cassandra, dữ liệu được phân phối theo **partition key**. Mỗi giá trị partition key hoàn chỉnh xác định một **phân vùng logic**, chứa một hoặc nhiều hàng được phân biệt bằng các **clustering columns**. Khi một phân vùng tích lũy quá nhiều hàng, quá nhiều giá trị/cell hoặc payload quá lớn, Cassandra có thể gặp tình trạng **large partition**. Trong nhiều tài liệu, khái niệm **wide row** cũng được dùng để chỉ cấu trúc dữ liệu có rất nhiều cột/cell trong cùng một phân vùng; cách gọi này có nguồn gốc từ mô hình lưu trữ Cassandra đời đầu.

Một phân vùng lớn có thể làm chậm truy vấn, tăng khối lượng đọc SSTable, làm nặng compaction và repair. Tuy nhiên, **phân vùng lớn** khác với **phân vùng nóng** (*hot partition*): phân vùng nhỏ cũng có thể bị quá tải vì được truy cập liên tục. Thiết kế bảng wide-column theo truy vấn cần kiểm soát **kích thước, hình dạng, vòng đời dữ liệu và lưu lượng** cùng lúc.

Bài học thuộc chủ đề **Khóa và phân vùng** này giải thích cơ chế, triệu chứng, cách đo và cách xử lý để truy vấn CQL và ứng dụng Java hoạt động ổn định trong hệ thống phân tán có replication, consistency level và các hoạt động nền như compaction/repair.

Sau bài học, bạn có thể:

- Phân biệt large partition, wide row, large cell và hot partition.
- Giải thích tác động của phân vùng lớn lên **đọc**, **ghi**, **compaction**, **streaming** và **repair**.
- Hiểu tại sao `LIMIT`, paging, tăng replication factor hay `ALLOW FILTERING` không giải quyết tận gốc một khóa phân vùng kém.
- Thiết kế lại partition key theo bucket thời gian hoặc shard có kiểm soát, đồng thời giữ được đường truy vấn chính.
- Sử dụng thông số quan sát vận hành để nhận diện phân vùng bất thường.
- Viết truy vấn CQL và Java Driver đọc đúng phân vùng, đúng khoảng và có giới hạn.

## 1. Thế nào là phân vùng lớn và hàng rộng?

Một bảng Cassandra có partition key và có thể có clustering columns:

```sql
CREATE TABLE events_by_device (
    tenant_id    text,
    device_id    uuid,
    occurred_at  timestamp,
    event_id     uuid,
    event_type   text,
    payload      text,
    PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Với thiết kế này, **mỗi cặp `(tenant_id, device_id)` là một phân vùng**. Tất cả sự kiện của thiết bị trong mọi ngày cùng ở phân vùng đó:

```text
Partition ('acme', device-A)
│
├── 2026-11-21T10:00Z, event-1001 → payload
├── 2026-11-21T09:59Z, event-1000 → payload
├── 2026-11-21T09:58Z, event-0999 → payload
│   ...
├── 2026-10-01T07:05Z, event-0200 → payload
│   ...
└── 2025-11-21T00:00Z, event-0001 → payload
    ↑ Số hàng/cell tăng theo thời gian nếu không giới hạn vòng đời
```

Đây là một phân vùng **rộng theo số clustering rows**. Nó có thể trở thành large partition khi số hàng/cell và byte khiến truy vấn hoặc công tác vận hành tốn tài nguyên vượt khả năng dự kiến.

### Phân biệt các thuật ngữ

| Thuật ngữ | Mô tả | Ví dụ |
| --- | --- | --- |
| **Large partition** | Phân vùng có nhiều dữ liệu/cell và footprint lớn; mức “lớn” phải gắn với workload và phiên bản Cassandra. | Một thiết bị tích lũy nhiều năm sự kiện trong một partition key. |
| **Wide row** | Thuật ngữ lịch sử cho cấu trúc có rất nhiều cột/cell liên quan một khóa; trong mô hình CQL thường tương ứng nhiều clustering rows trong một phân vùng. | Một `device_id` có hàng triệu bộ `(occurred_at, event_id)`. |
| **Large cell/value** | Một giá trị đơn lẻ chứa nhiều byte, ví dụ `blob`/`text` rất dài. | Một bản ghi chứa ảnh 10 MiB. |
| **Hot partition** | Một khóa nhận quá nhiều request đọc/ghi tại một thời điểm, ngay cả khi byte còn nhỏ. | Một phiên giao dịch đang được hàng nghìn client cập nhật liên tục. |
| **Tombstone-heavy partition** | Có nhiều dấu xóa/giá trị đã hết TTL, làm công việc đọc phức tạp hơn số hàng sống cho thấy. | Nhiều sự kiện bị xóa theo lô hoặc TTL hết hạn dồn dập. |

Cassandra **không** tự tạo thêm tên cột CQL mỗi khi có hàng clustering mới. Vì vậy, “wide row” không đồng nghĩa khai báo nhiều cột trong `CREATE TABLE`. Cần nhìn số clustering rows, cấu trúc collection, cell và byte thực tế.

> **Nguyên tắc:** tổng dung lượng của **bảng** không cho biết bảng có large partition hay không. Một bảng 20 TB được chia thành rất nhiều phân vùng vừa phải có thể dễ vận hành hơn bảng nhỏ chứa vài phân vùng rất lớn.

## 2. Tại sao partition key khiến dữ liệu và tải bị tập trung?

Cassandra dùng partitioner (thường là `Murmur3Partitioner`) để tính **token từ toàn bộ partition key**, sau đó dùng chiến lược replication để chọn các node giữ bản sao.

```text
Cặp (tenant_id, device_id)
          |
          v
    Hash ra token
          |
          v
    Tập replica phụ trách
       /     |      \
    Node A  Node B  Node C  (minh họa RF = 3)
          |
          v
   Các clustering rows của partition
```

Các hàng có cùng partition key không được chia theo từng clustering key sang các tập replica ngẫu nhiên. Vì vậy:

1. Mỗi replica chịu trách nhiệm phải có khả năng chứa và xử lý dữ liệu của phân vùng.
2. Nếu một partition key cực nóng, tập replica của nó cũng chịu tải tập trung.
3. Tăng `replication factor` tạo thêm bản sao; điều đó **không chia nhỏ một partition key thành nhiều phân vùng độc lập**.
4. Clustering order và range query có thể giúp đọc **một đoạn** hiệu quả trong phân vùng, nhưng không làm phân vùng tự ngừng phình to.

**Đừng đồng nhất “cùng phân vùng” với “một khối liên tục trên đĩa”.** Cassandra dùng LSM tree: ghi đến commit log/memtable, flush thành SSTable; một partition có thể hiện diện ở nhiều SSTable. Khi đọc, replica ghép phiên bản hợp lệ và dữ liệu theo thứ tự clustering. Đây là lý do lịch sử ghi, compaction và tombstone ảnh hưởng chi phí đọc.

## 3. Large partition hình thành theo những cách nào?

### Tích lũy sự kiện vô hạn theo một khóa

Ví dụ `PRIMARY KEY (device_id, occurred_at, event_id)` cho phép lấy timeline theo thiết bị, nhưng tất cả lịch sử của thiết bị dồn vào cùng một partition key. Nếu không có bucket thời gian, số hàng và dữ liệu sống có thể tăng mãi.

### Một khóa có cardinality rất thấp

```sql
-- Ví dụ dễ tạo phân vùng lớn khi toàn hệ thống chỉ có vài status:
PRIMARY KEY (status, updated_at, customer_id)
```

Ở đây chỉ `status` là partition key. Một status phổ biến như `ACTIVE` có thể chứa hàng triệu khách hàng. Việc dùng `status` làm khóa chọn phân vùng chỉ hợp lý nếu đã chứng minh lượng dữ liệu và tải cho mỗi giá trị đều ở mức chấp nhận được.

### Dùng payload quá lớn trong từng hàng

```sql
CREATE TABLE files_by_account (
    account_id uuid,
    uploaded_at timestamp,
    file_id uuid,
    file_content blob,
    PRIMARY KEY (account_id, uploaded_at, file_id)
);
```

Chỉ vài nghìn hàng nhưng mỗi `file_content` có thể hàng megabyte đã tạo footprint rất lớn. Với nội dung nhị phân lớn, cân nhắc lưu trong object storage và lưu **định danh, đường dẫn, checksum, metadata** trong Cassandra.

### Nhiều collection cell hoặc cập nhật/xóa thường xuyên

Cột `map`/`set`/`list` không `frozen` có thể gồm nhiều phần tử được quản lý ở mức cell; collection không giới hạn tăng trưởng dễ làm một hàng/phân vùng quá rộng. Cập nhật và xóa liên tục có thể tạo nhiều tombstone trước khi đủ điều kiện dọn dẹp.

### Phân bố dữ liệu lệch

Một số tenant hoặc thiết bị tạo nhiều sự kiện gấp hàng nghìn lần mức trung bình. Bucket theo ngày có thể vừa cho thiết bị bình thường nhưng vẫn quá lớn đối với thiết bị “siêu nóng”. **Chỉ đo giá trị trung bình của toàn bảng thường che mất các phân vùng xấu nhất.**

## 4. Phân vùng lớn ảnh hưởng đến đường đọc như thế nào?

Truy vấn hiệu quả của Cassandra thường gồm hai bước: chọn **đúng partition key**, rồi đọc **dải clustering keys** cần thiết.

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_device
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
LIMIT 20;
```

Nhờ `occurred_at DESC`, truy vấn trên có thể lấy 20 hàng mới nhất theo thứ tự clustering mà không cần đọc toàn bộ lịch sử. Do đó, **large partition không đồng nghĩa mọi truy vấn đều phải quét toàn partition**.

Tuy vậy, các tình huống sau vẫn có thể tốn kém:

- **Quét phạm vi rộng:** truy vấn toàn bộ lịch sử hoặc một khoảng chứa hàng triệu hàng khiến replica đọc/giải mã nhiều dữ liệu, mạng truyền nhiều và ứng dụng xử lý lâu.
- **Nhiều SSTable cùng chứa một partition:** read path có thể cần kiểm tra, merge các phiên bản và tombstone từ nhiều nguồn; chiến lược compaction ảnh hưởng chi phí.
- **Tombstone dày:** query trả ít hàng sống nhưng phải vượt qua nhiều tombstone/xóa/hết TTL để tìm hàng hợp lệ.
- **Cell hoặc payload lớn:** đọc ít hàng nhưng mỗi hàng chuyển nhiều byte, gây áp lực bộ nhớ, I/O, mạng và serialization.
- **Concurrent read:** nhiều client cùng truy vấn một partition có thể gây hàng đợi trên tập replica, kể cả mỗi request đã có `LIMIT`.

So sánh:

| Câu truy vấn | Phạm vi công việc logic | Rủi ro |
| --- | --- | --- |
| Đầy đủ partition key, `LIMIT 20` và đọc theo clustering mới nhất | Tập trung vào phần đầu dải, có khả năng dừng sớm | Thường hợp lý, nhưng tombstone và SSTable vẫn ảnh hưởng. |
| Đầy đủ partition key và khoảng 5 phút | Đọc một slice clustering tương ứng | Hợp lý nếu 5 phút có số hàng và cell vừa phải. |
| Đầy đủ partition key nhưng không giới hạn ngày/số hàng | Có thể đọc một lượng dữ liệu rất lớn | Latency, bộ nhớ và mạng tăng. |
| Không đủ partition key, thêm `ALLOW FILTERING` | Có thể cần lọc nhiều phân vùng | Chi phí khó dự đoán, dễ quá tải. |
| `SELECT COUNT(*)` trên một partition khổng lồ | Phải xử lý các hàng/cell liên quan để đếm | Không nên dùng để giám sát thường xuyên dưới tải cao. |

### Vì sao `LIMIT` và paging chỉ giải quyết một phần?

`LIMIT 100` giới hạn số **hàng kết quả**, không bảo đảm chỉ có 100 cell được đọc từ SSTable. Với tombstone, Cassandra có thể phải duyệt nhiều mục hơn số hàng trả về.

**Driver paging** chia luồng kết quả thành nhiều trang để giảm kích thước phản hồi và giữ bộ nhớ phía ứng dụng trong mức kiểm soát. Nó không chia dữ liệu đang lưu thành những phân vùng nhỏ hơn. Nếu ứng dụng đọc hết hàng triệu kết quả qua nhiều trang, tổng chi phí đọc vẫn lớn.

## 5. Phân vùng lớn ảnh hưởng đến ghi như thế nào?

Cassandra được tối ưu cho ghi tuần tự qua commit log và memtable, nên **một lệnh ghi vào phân vùng đang lớn không tự động phải quét cả phân vùng đó**. Phân biệt hai tình huống quan trọng:

- **Một mutation nhỏ** ghi một vài cell vào một partition lớn: vẫn có thể nhanh vì đường ghi ban đầu không cần đọc toàn bộ hàng.
- **Một mutation/batch rất lớn** hoặc luồng ghi quá dày vào cùng partition: có thể gây áp lực về kích thước mutation, bộ nhớ, compaction và tập replica phục vụ khóa đó.

Các hậu quả phổ biến:

1. **Hotspot trên replica:** mọi ghi của một partition key đi đến tập replica chịu trách nhiệm; nhiều client ghi dồn vào cùng khóa gây CPU, I/O, hàng đợi và độ trễ.
2. **Flush và compaction:** phiên bản/cell ghi liên tiếp trải trên nhiều memtable/SSTable; hệ thống cần hợp nhất hoặc quản lý chúng về sau.
3. **Write amplification và tombstone:** cập nhật/xóa nhiều lần tạo thêm phiên bản/tombstone, làm tăng công việc lưu trữ nền.
4. **Mutation lớn:** cập nhật một collection rất lớn hoặc batch quá nhiều thao tác có thể vượt các ngưỡng cảnh báo/từ chối tùy phiên bản, gây GC/memory pressure.
5. **Retry và định danh:** dùng `now()` hay UUID mới mỗi lần retry có thể sinh thêm clustering rows, khiến phân vùng lớn nhanh hơn số sự kiện nghiệp vụ thực tế.

### BATCH có sửa được vấn đề?

Không. Dùng `BEGIN BATCH` để nhồi hàng nghìn thao tác vào một request **không chia nhỏ phân vùng** và có thể tạo mutation/batch lớn. Batch trong Cassandra có mục đích semantics phù hợp với các thao tác có liên quan, không phải một cách tăng throughput tổng quát.

Đối với ghi nhiều sự kiện độc lập, thường nên dùng **prepared statements và ghi bất đồng bộ có giới hạn concurrency**, tổ chức partition key/bucket thích hợp và theo dõi độ trễ, thay vì gom dữ liệu khổng lồ vào một batch.

## 6. Ảnh hưởng đến compaction, repair và streaming

Một bảng Cassandra tiếp tục hoạt động khi dữ liệu được flush, compact, sao chép và sửa chữa sai khác giữa các replica. Phân vùng rất lớn làm các hoạt động này khó kiểm soát hơn:

| Hoạt động | Tác động khi phân vùng lớn |
| --- | --- |
| **Compaction** | Có thể cần xử lý nhiều dữ liệu/phiên bản/tombstone; tăng I/O, CPU, thời gian và không gian đĩa tạm tùy chiến lược compaction. |
| **Repair** | Đồng bộ giữa các replica phải xét lượng dữ liệu lớn; repair có thể tốn băng thông, I/O và thời gian, nhất là khi một replica thiếu nhiều dữ liệu. |
| **Streaming/bootstrap/decommission** | Di chuyển dữ liệu theo phạm vi token có thể kéo theo phân vùng rất lớn, ảnh hưởng tốc độ chuyển và cân bằng tải. |
| **Read repair/đọc nhất quán** | Đọc từ nhiều replica khi cần so sánh/đối chiếu có thể tốn chi phí hơn nếu truy cập một phần dữ liệu lớn hoặc có sai khác. |
| **Backup và restore** | Kích thước, số SSTable và việc chuyển dữ liệu ảnh hưởng thời gian sao lưu/khôi phục; dữ liệu rất lớn cần được dự trù. |

Chi tiết phụ thuộc **phiên bản Cassandra, topology, compaction strategy, replication strategy và kiểu tải**. Không phải một phân vùng lớn luôn làm toàn bộ repair thất bại, nhưng nó làm tăng rủi ro về đuôi độ trễ và chi phí vận hành.

**Điều không nên hiểu nhầm:** chạy compaction hoặc repair **không thay đổi partition key**. Chúng có thể cải thiện tình trạng SSTable/tombstone hoặc đồng bộ replica nhưng không chia một phân vùng quá rộng thành nhiều phân vùng nhỏ.

## 7. Ví dụ định lượng: vì sao cùng một thiết bị có thể tạo “wide row”?

Giả sử một thiết bị phát sinh **500 sự kiện/giây** vào giờ cao điểm, mỗi sự kiện chứa **800 byte payload logic**, không tính khóa, metadata, nén, tombstone.

```text
1 phút:
  500 × 60 = 30.000 hàng
  30.000 × 800 B = 24.000.000 B ≈ 22,9 MiB payload

1 giờ:
  500 × 3.600 = 1.800.000 hàng
  1.800.000 × 800 B = 1.440.000.000 B ≈ 1,34 GiB payload

24 giờ liên tục ở tốc độ này:
  43.200.000 hàng
  34.560.000.000 B ≈ 32,2 GiB payload
```

Nếu partition key chỉ là `(tenant_id, device_id)`, **một phân vùng** của thiết bị có thể tích lũy hơn 32 GiB payload chỉ sau một ngày theo giả định cực đoan này. Mỗi replica phụ trách phải lưu dữ liệu tương ứng.

Nếu `replication factor = 3`, có ba bản sao logic trên cluster theo chiến lược replication; **không nên đồng nhất 32,2 × 3 GiB với chính xác số byte đĩa**, vì footprint thực còn chịu ảnh hưởng compression, SSTable, compaction, overhead và dữ liệu đã xóa.

### Chọn bucket theo tải

| Bucket cho một thiết bị | Hàng/bucket | Payload giả định/bucket |
| --- | ---: | ---: |
| 1 ngày | 43.200.000 | ≈ 32,2 GiB |
| 1 giờ | 1.800.000 | ≈ 1,34 GiB |
| 5 phút | 150.000 | ≈ 114,4 MiB |
| 1 phút | 30.000 | ≈ 22,9 MiB |

Không có “định mức tối ưu” chung cho mọi cluster. Bảng chỉ để chứng minh: **với thiết bị này**, bucket ngày hoặc giờ có thể quá rộng, trong khi bucket phút giảm kích thước mỗi partition nhưng làm tăng số phân vùng phải truy vấn cho lịch sử dài.

Ngoài **giá trị trung bình**, phải tính **mức đỉnh** và các thiết bị có dữ liệu bất thường. Dù chia bucket phút, một thiết bị nhận 500 sự kiện/giây vẫn có thể tạo **hot partition** trong chính phút đang ghi. Khi đó cần cân nhắc shard/balancing hoặc kiến trúc ingest phù hợp.

## 8. Thiết kế lại bảng theo bucket thời gian

Giả sử yêu cầu đọc chính là: **“Lấy 100 sự kiện mới nhất của thiết bị trong một phút”** hoặc **“Lấy các sự kiện của thiết bị từ 08:10:00 đến trước 08:10:30 UTC”**.

Một thiết kế phù hợp có thể là:

```sql
CREATE TABLE events_by_device_minute (
    tenant_id     text,
    device_id     uuid,
    minute_bucket timestamp,
    occurred_at   timestamp,
    event_id      uuid,
    event_type    text,
    payload       text,
    PRIMARY KEY (
        (tenant_id, device_id, minute_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
```

Ở đây:

- Partition key ghép: `(tenant_id, device_id, minute_bucket)`. Mỗi thiết bị trong mỗi phút UTC là một phân vùng logic.
- Clustering columns: `occurred_at`, `event_id`, hỗ trợ sắp thời gian và nhiều sự kiện trùng timestamp.
- `minute_bucket` phải được tính theo **cùng quy tắc** ở producer và consumer, chẳng hạn đầu phút UTC (giây và nano = 0).
- `event_id` nên ổn định giữa các lần retry để tránh tạo sự kiện trùng do gửi lại.

### Ghi một sự kiện

```sql
INSERT INTO events_by_device_minute (
    tenant_id, device_id, minute_bucket,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:10:00Z',
    '2026-11-21T08:10:12Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'temperature',
    'sensor=42.1'
);
```

### Đọc theo khoảng bên trong một phân vùng

```sql
SELECT occurred_at, event_id, event_type, payload
FROM events_by_device_minute
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND minute_bucket = '2026-11-21T08:10:00Z'
  AND occurred_at >= '2026-11-21T08:10:00Z'
  AND occurred_at <  '2026-11-21T08:10:30Z'
LIMIT 100;
```

Đây là **một partition lookup và một clustering range**. Khoảng đóng–mở `[start, end)` tránh trùng hàng đúng ranh giới khi ghép các đoạn kế tiếp.

**Điểm đánh đổi:** truy vấn từ 08:10 đến 08:20 phải đọc các phân vùng phút liên quan rồi hợp nhất kết quả; `CLUSTERING ORDER BY` chỉ áp dụng **trong từng partition**. Truy vấn lịch sử nhiều ngày không nên mở hàng nghìn read requests vô hạn cùng lúc; phải giới hạn concurrency, có phân trang hoặc tạo mô hình tổng hợp riêng theo nhu cầu đọc.

### Khi bucket thời gian chưa đủ: shard có kiểm soát

Một partition phút có thể vẫn nóng. Khi cần, có thể bổ sung `shard_id` được tính theo quy tắc ổn định:

```sql
-- Ví dụ khóa để phân tán tải theo shard trong mỗi phút:
PRIMARY KEY (
    (tenant_id, device_id, minute_bucket, shard_id),
    occurred_at,
    event_id
)
```

Ứng dụng ghi cần chọn shard nhất quán cho sự kiện; ứng dụng đọc phải biết hoặc truy vấn **đủ các shard** tương ứng rồi gộp dữ liệu. Số shard cần dựa trên tải và chi phí fan-out; thêm shard tùy tiện có thể làm đọc khó hơn đáng kể.

Không có đảm bảo “mỗi shard nằm trên node riêng” vì token phân phối có thể dẫn đến cùng node/replica; mục tiêu là cải thiện độ phân bố thống kê trên nhiều partition keys.

## 9. Đọc/ghi an toàn khi chuyển từ bảng cũ sang bảng mới

Với bảng đang tồn tại, thay partition key thường đòi hỏi **tạo bảng mới và chuyển dữ liệu**, không chỉ `ALTER TABLE`.

Một quy trình triển khai có kiểm soát:

1. **Định nghĩa truy vấn mục tiêu và bucket** bằng số liệu sản xuất; chọn partition key mới và clustering columns đủ định danh hàng.
2. **Tạo bảng mới** và triển khai writer biết tính bucket thống nhất, dùng event ID ổn định khi retry.
3. **Lập kế hoạch dữ liệu lịch sử**: backfill có giới hạn throughput; giữ checkpoint để retry mà không nhân đôi sự kiện.
4. **Đảm bảo dữ liệu ghi trong giai đoạn chuyển đổi**: dual-write có giám sát hoặc cơ chế replay từ nguồn sự kiện; không mặc định hai bảng được cập nhật nguyên tử.
5. **Đọc kiểm chứng** theo nhiều key/bucket và so sánh dữ liệu, bao gồm ranh giới thời gian, TTL và trạng thái xóa.
6. **Chuyển read path** sau khi dữ liệu/độ trễ đáp ứng yêu cầu; theo dõi metrics và xử lý ngoại lệ.
7. **Dừng ghi bảng cũ, lưu/loại bỏ dữ liệu theo chính sách** sau khi đã xác nhận người dùng không còn phụ thuộc.

Một lỗi thường gặp là tính `minute_bucket` theo múi giờ cục bộ lúc ghi nhưng theo UTC lúc đọc. Hai phía khi đó truy vấn **khác partition keys**, có thể thấy “mất dữ liệu” dù bản ghi đã tồn tại.

Không cần sửa compaction strategy hoặc tăng consistency level chỉ để hy vọng một phân vùng to tự chia nhỏ: giải pháp căn bản là **thay hình dạng khóa và vòng đời lưu trữ**.

## 10. TTL, tombstone và compaction: kiểm soát vòng đời dữ liệu

Nếu chỉ cần lưu sự kiện trong 7 ngày, có thể dùng TTL ngay lúc ghi:

```sql
INSERT INTO events_by_device_minute (
    tenant_id, device_id, minute_bucket,
    occurred_at, event_id, event_type, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:10:00Z',
    '2026-11-21T08:10:12Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'temperature',
    'sensor=42.1'
) USING TTL 604800;
```

`604800` giây tương đương 7 ngày. Nhưng TTL **không có nghĩa dữ liệu biến mất tức thời khỏi mọi SSTable**. Dữ liệu hết hạn được xem là không còn sống khi đọc, và việc dọn tombstone khỏi đĩa phụ thuộc điều kiện an toàn cùng compaction.

Một số cân nhắc:

- Chọn **bucket hợp lý** để hạn chế kích thước ngay từ thời điểm ghi, thay vì chỉ dựa vào TTL.
- Tránh xóa lẻ hàng triệu hàng trong một phân vùng nếu có cách tổ chức dữ liệu theo vòng đời dễ dọn hơn.
- Đánh giá compaction strategy phù hợp: chẳng hạn **TimeWindowCompactionStrategy (TWCS)** thường được cân nhắc cho dữ liệu chuỗi thời gian có TTL và cửa sổ ghi phù hợp; nó không thay partition key hoặc loại bỏ mọi rủi ro tombstone.
- Ghi ngược thời gian, cập nhật sự kiện cũ hoặc TTL không đồng đều có thể làm các giả định tối ưu của mô hình time-series/compaction khó đạt được.
- Repair và cấu hình tombstone/`gc_grace_seconds` cần phù hợp với chính sách vận hành để tránh nguy cơ dữ liệu đã xóa xuất hiện trở lại khi replica bỏ lỡ xóa. Không giảm tùy tiện `gc_grace_seconds` chỉ để giải quyết cảnh báo dung lượng.

**Thực tế:** nhiều tombstone có thể khiến một query có `LIMIT 10` vẫn phải duyệt lượng dữ liệu đáng kể. Vì vậy cần kết hợp time bucketing, TTL, kiểm soát cập nhật/xóa và theo dõi đọc.

## 11. Đo và chẩn đoán phân vùng lớn trên hệ thống

Các công cụ và metric hữu ích phụ thuộc phiên bản Cassandra; tên field có thể thay đổi. Với một keyspace/bảng giả định:

```bash
# Thống kê tổng quan theo bảng tại một node:
nodetool tablestats app_ks.events_by_device_minute

# Histogram về kích thước phân vùng và số cell, kèm thống kê độ trễ:
nodetool tablehistograms app_ks events_by_device_minute
```

Cần quan sát các nhóm số liệu:

| Nhóm số liệu | Ý nghĩa chẩn đoán |
| --- | --- |
| **Partition size min/mean/max hoặc histogram** | Nhận diện phần đuôi lớn và phân vùng ngoại lệ; trung bình thấp không loại trừ phân vùng cực lớn. |
| **Cell count histogram** | Đánh giá độ rộng nội bộ; cần phân biệt số cell với số cột khai báo trong schema. |
| **Read/write latency và tỷ lệ timeout** | Đo tác động lên người dùng; so sánh p95/p99 và đỉnh tải. |
| **SSTables per read / pending compactions** | Gợi ý read amplification và hoạt động nền chưa bắt kịp tốc độ ghi. |
| **Tombstones scanned / cảnh báo tombstone** | Phân biệt ít kết quả sống với nhiều dữ liệu phải duyệt. |
| **Cảnh báo large partition trong log** | Giúp xác định bảng hoặc partition key đáng điều tra, tùy khả năng log/cấu hình phiên bản. |
| **CPU, I/O, GC và mạng theo node** | Xác định replica chịu hotspot hoặc cạn tài nguyên. |

Các con số partition size từ công cụ có thể là **số liệu thống kê trên SSTable/compaction**, không phải phép đo tuyệt đối và tức thời của mỗi phân vùng logic còn sống. Cassandra có nhiều replica và nhiều SSTable; cần so sánh **cùng thời điểm, cùng phiên bản, cùng phạm vi đo**.

### Chẩn đoán theo trình tự

1. **Từ triệu chứng:** xác định query chậm, p99, timeout, node/replica bị tải cao, thời điểm xảy ra.
2. **Đối chiếu keyspace/bảng:** quan sát histogram size/cell, số SSTable per read, tombstone và compaction backlog.
3. **Xem phân bố truy cập:** có một số partition keys nhận phần lớn request không? Có một số outlier về byte/hàng không?
4. **Kiểm tra truy vấn:** có đủ partition key không, khoảng clustering rộng đến đâu, `LIMIT`/paging có được dùng đúng mục đích không?
5. **Kiểm tra vòng đời dữ liệu:** TTL, xóa hàng loạt, cập nhật collection, backfill và repair gần đây.
6. **Thử tải mô hình mới:** cùng workload, bucket/shard mới có giảm độ lớn hoặc hotspot mà không làm query fan-out quá lớn không?

Tránh dùng `SELECT COUNT(*)` để đếm mọi hàng của phân vùng cực lớn dưới tải cao: Cassandra phải xử lý rất nhiều dữ liệu để đếm. Tận dụng metrics/histogram hoặc dữ liệu thống kê từ luồng ghi khi có thể.

### Có ngưỡng MB/hàng nào là “an toàn tuyệt đối” không?

**Không có một ngưỡng áp dụng cho tất cả hệ thống.** Ngưỡng cảnh báo, khả năng chịu tải và giới hạn cấu hình có thể khác giữa phiên bản Cassandra và phần cứng. Nên xác lập **guardrail** dựa trên phân bố thực tế của row count, cell count, byte/partition, độ trễ SLO, đỉnh tải và ngân sách compaction/repair.

## 12. Truy vấn có giới hạn từ Java Driver

Ví dụ Java Driver 4.x dùng `PreparedStatement` để đọc một slice trong **một bucket phút**. `Instant` ánh xạ tới cột CQL `timestamp` và được dùng nhất quán cho thời điểm UTC.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class DeviceEventRepository {
    private final CqlSession session;
    private final PreparedStatement readInMinute;

    public DeviceEventRepository(CqlSession session) {
        this.session = session;
        this.readInMinute = session.prepare(
            "SELECT occurred_at, event_id, event_type, payload " +
            "FROM events_by_device_minute " +
            "WHERE tenant_id = ? AND device_id = ? AND minute_bucket = ? " +
            "AND occurred_at >= ? AND occurred_at < ? " +
            "LIMIT 100"
        );
    }

    public ResultSet findRangeInOneMinute(
            String tenantId, UUID deviceId,
            Instant startInclusive, Instant endExclusive) {

        Instant bucket = startInclusive.truncatedTo(ChronoUnit.MINUTES);
        Instant bucketEnd = bucket.plus(1, ChronoUnit.MINUTES);

        if (!startInclusive.isBefore(endExclusive) ||
            endExclusive.isAfter(bucketEnd)) {
            throw new IllegalArgumentException(
                "Khoang doc phai nam trong mot bucket phut UTC");
        }

        BoundStatement statement = readInMinute.bind(
            tenantId, deviceId, bucket, startInclusive, endExclusive
        ).setPageSize(50);

        return session.execute(statement);
    }
}
```

Trong đoạn mã:

- `startInclusive` và `endExclusive` tạo khoảng thời gian **`[start, end)`**.
- Hàm kiểm tra đầu vào để không vô tình truy vấn chỉ một bucket khi khoảng đọc đã vượt sang phút tiếp theo.
- Tất cả thành phần partition key đều xuất hiện trong `WHERE`.
- `LIMIT 100` là giới hạn **tổng số hàng trả về**, còn `setPageSize(50)` là kích thước trang driver mong muốn.
- `ResultSet` có thể tự fetch các trang tiếp theo khi duyệt kết quả; application nên dừng ở số hàng cần thiết, tránh `all()` với query không giới hạn.
- Nếu cần đọc nhiều phút, tầng dịch vụ phải phân chia khoảng, giới hạn số truy vấn đồng thời và hợp nhất kết quả.

Với luồng ghi throughput cao, nên tạo ID sự kiện ổn định để retry không sinh thêm hàng. Đối với tác vụ backfill hoặc cần cập nhật trong nhiều partition keys, hãy kiểm soát concurrency và khả năng khôi phục khi một phần thao tác thành công.

## 13. Các hiểu lầm cần tránh

| Khẳng định | Vấn đề | Cách hiểu/giải pháp |
| --- | --- | --- |
| “Bảng có nhiều cột trong schema nên chắc chắn là wide row.” | Số cột schema không đo được hàng triệu clustering rows và payload. | Đo số hàng/cell/byte theo **partition key**. |
| “Có `LIMIT 10` nên partition 5 GiB không sao.” | Kết quả ít không bảo đảm mọi query/range, tombstone, compaction hay repair đều nhẹ. | Kiểm soát kích thước và vòng đời partition; đo thực tế. |
| “Partition lớn thì mỗi `INSERT` đều phải quét 5 GiB.” | Ghi ban đầu thường vào commit log/memtable, không quét cả partition. | Phân biệt write path ban đầu với hotspot và chi phí nền. |
| “Tăng replication factor chia partition thành nhiều phần.” | Replica là bản sao của cùng dữ liệu logic. | Muốn chia dữ liệu cần đổi partition key/bucket/shard. |
| “Thêm `ALLOW FILTERING` để query không khớp khóa vẫn nhanh.” | Lọc rộng có thể rất đắt và khó dự đoán. | Thiết kế bảng theo truy vấn. |
| “Sửa compaction strategy sẽ hết large partition.” | Compaction tối ưu tệp, không đổi logic partition key. | Đo và chia dữ liệu tại mô hình khóa. |
| “TTL 7 ngày thì dữ liệu bị xóa sạch trên đĩa ngay ngày thứ 7.” | TTL tạo hết hạn logic; dọn dẹp vật lý phụ thuộc tombstone/compaction. | Kết hợp bucket, TTL và chiến lược compaction. |
| “Bucket phút luôn tốt hơn bucket ngày.” | Bucket nhỏ gây nhiều partition và nhiều truy vấn fan-out. | Chọn theo tốc độ ghi, kiểu đọc và SLO. |
| “Hot partition và large partition là cùng một lỗi.” | Một lỗi do byte/cell, một lỗi do tải truy cập. | Kiểm tra cả size histogram và lưu lượng/latency. |

## 14. Bài tập tình huống

Một nền tảng IoT có bảng:

```sql
CREATE TABLE device_messages (
    device_id uuid,
    created_at timestamp,
    message_id uuid,
    payload text,
    PRIMARY KEY (device_id, created_at, message_id)
);
```

Một nhóm thiết bị phổ thông gửi **2 bản tin/giây**, nhưng thiết bị công nghiệp cao điểm gửi **300 bản tin/giây**, payload trung bình **1 KiB/bản tin**. Yêu cầu đọc gồm:

- Trang dashboard: **50 bản tin mới nhất** của một thiết bị.
- Điều tra sự cố: bản tin trong **15 phút** được chọn.
- Báo cáo: số bản tin theo **ngày**.

Hãy trả lời:

1. Thiết bị công nghiệp tạo bao nhiêu hàng trong 15 phút nếu mỗi sự kiện có primary key riêng?
2. Payload logic trong 15 phút xấp xỉ bao nhiêu MiB?
3. Với partition key chỉ là `device_id`, dữ liệu một thiết bị sẽ tích lũy theo thời gian hay tự chia theo ngày?
4. Bucket 15 phút có thể phục vụ điều tra một khoảng bất kỳ dài 15 phút bằng đúng một partition lookup không?
5. Nếu 50 bản tin mới nhất nằm sát ranh giới hai bucket, ứng dụng phải làm gì?
6. Tăng `replication factor` từ 3 lên 5 có làm mỗi partition nhỏ lại không?
7. Một query trả 10 hàng mà vẫn chậm nên kiểm tra điều gì ngoài số hàng trả về?
8. Để tổng hợp báo cáo ngày trên dữ liệu rất lớn, có nên `COUNT(*)` toàn bộ hàng ngày từ bảng sự kiện mỗi lần dashboard làm mới không?

**Đáp án gợi ý:**

1. `300 × 60 × 15 = 270.000` hàng.
2. `270.000 KiB / 1.024 ≈ 263,7 MiB` payload, chưa tính overhead, replica và nén.
3. Dữ liệu **tích lũy trong cùng partition** của `device_id`; các clustering columns không tự chia partition.
4. **Không chắc**. Một khoảng dài 15 phút có thể nằm lệch ranh giới và cắt qua **hai bucket** 15 phút.
5. Đọc đủ bucket liên quan, hợp nhất theo clustering timestamp và ID, rồi lấy 50 bản tin mới nhất theo thứ tự chung.
6. **Không**. Tăng RF chỉ làm tăng số bản sao; partition key và footprint logic mỗi replica không đổi.
7. Kiểm tra tombstone, số SSTable cần đọc, read latency, payload/cell lớn, replica nóng, compaction backlog và điều kiện clustering.
8. Thường **không**. Nên cân nhắc bảng thống kê/tổng hợp được cập nhật có kiểm soát theo yêu cầu chính xác và độ trễ.

Tình huống cho thấy cần cân bằng **số hàng mỗi bucket**, **payload**, **tần suất ghi/đọc** và **chi phí fan-out**. Lựa chọn cuối cùng nên được kiểm chứng bằng workload thực tế.

## 15. Nguyên tắc mang vào vận hành

- **Large partition** là vấn đề về kích thước và cấu trúc dữ liệu dưới một partition key; **wide row** thường mô tả độ rộng do nhiều clustering rows/cell.
- **Hot partition** là vấn đề tập trung tải. Một phân vùng có thể lớn, nóng, cả hai hoặc không thuộc nhóm nào.
- Đọc dải clustering hẹp trong large partition đôi khi vẫn hiệu quả, nhưng **LIMIT/paging không giải quyết** chi phí quét rộng, tombstone, compaction, repair hay lưu trữ.
- Ghi nhỏ vào một large partition không tự yêu cầu quét cả phân vùng; điểm nghẽn phát sinh từ throughput tập trung, mutation lớn và các công việc nền.
- Muốn giới hạn kích thước lâu dài cần **đổi mô hình partition key**, thường là bucket theo thời gian, đôi khi thêm shard và quy tắc đọc kèm theo.
- Quan sát **phần đuôi phân bố partition size/cell count**, timeout, p99 latency, tombstones, SSTable/compaction và tải replica.
- Chọn TTL, compaction strategy, replication và consistency theo nhu cầu hệ thống, nhưng **không xem chúng như cách thay thế thiết kế khóa đúng**.

Khi hiểu ảnh hưởng của phân vùng lớn lên cả đường đọc, đường ghi và công tác vận hành Cassandra, bạn có thể thiết kế bảng wide-column theo truy vấn bền vững hơn, kiểm soát độ trễ CQL, xác định cách chia dữ liệu và xây dựng ứng dụng Java có giới hạn tài nguyên rõ ràng.

