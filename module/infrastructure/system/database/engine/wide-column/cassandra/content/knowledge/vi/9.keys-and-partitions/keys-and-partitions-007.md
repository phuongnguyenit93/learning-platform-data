# Kích thước phân vùng theo số hàng, cột và dung lượng

Trong Apache Cassandra, **partition key** xác định nhóm dữ liệu được lưu trên cùng tập replica. Một phân vùng (*partition*) có thể chứa một hàng, hàng nghìn hàng hoặc nhiều triệu hàng. Điều quan trọng không chỉ là **có bao nhiêu hàng**, mà còn là **mỗi hàng chứa bao nhiêu dữ liệu và bao nhiêu cell**, các giá trị có được cập nhật/xóa thường xuyên không, và tải đọc/ghi có tập trung vào cùng partition key hay không.

Đối với cơ sở dữ liệu wide-column phân tán, thiết kế khóa phân vùng là một phần trực tiếp của quản lý kích thước, hiệu năng và khả năng vận hành. Một bảng có tổng dung lượng hàng terabyte vẫn có thể hoạt động tốt nếu dữ liệu và tải được phân bố hợp lý; ngược lại, chỉ một phân vùng quá lớn hoặc quá nóng cũng có thể gây chậm đọc, tăng chi phí compaction và tạo điểm nghẽn trên replica.

Bài học trong nhóm **Khóa và phân vùng** giải thích cách đánh giá một phân vùng theo **ba chiều: số hàng, số cột/cell và dung lượng byte**, sau đó áp dụng vào CQL, bucketing thời gian, replication, theo dõi vận hành và truy vấn từ Java.

Sau bài học, bạn có thể:

- Phân biệt **số hàng logic**, **số giá trị/cell** và **số byte lưu trữ** của một phân vùng Cassandra.
- Ước lượng quy mô phân vùng từ tốc độ ghi, số cột, kích thước dữ liệu và thời gian lưu.
- Hiểu vì sao **large partition** và **hot partition** là hai vấn đề liên quan nhưng khác nhau.
- Thiết kế partition key theo thực thể và bucket thời gian; tính số phân vùng phải đọc khi truy vấn nhiều bucket.
- Kiểm tra các số liệu vận hành về partition size và cell count mà không quét toàn bộ bảng.
- Viết truy vấn CQL và Java Driver để đọc có giới hạn với đúng partition key.

## 1. Một phân vùng chứa những gì?

Xét bảng ghi các chỉ số của thiết bị IoT:

```sql
CREATE TABLE readings_by_device (
    device_id    uuid,
    recorded_at  timestamp,
    reading_id   uuid,
    temperature  double,
    humidity     double,
    status       text,
    PRIMARY KEY (device_id, recorded_at, reading_id)
) WITH CLUSTERING ORDER BY (recorded_at DESC, reading_id ASC);
```

Trong bảng này:

- `device_id` là **partition key**.
- `recorded_at` và `reading_id` là **clustering columns**.
- `temperature`, `humidity` và `status` là **regular columns**.

Mỗi thiết bị có một phân vùng logic, chứa mọi bản đo của thiết bị đó trong vòng đời của bảng:

```text
Partition key = device-01
│
├── Hàng (2026-11-21 09:00, id-003) : temperature, humidity, status
├── Hàng (2026-11-21 08:59, id-002) : temperature, humidity, status
├── Hàng (2026-11-21 08:58, id-001) : temperature, humidity, status
└── ... nhiều ngày, nhiều tháng, nhiều năm ...
```

Tất cả hàng có cùng `device_id` thuộc cùng phân vùng logic. Cassandra tính token từ partition key, rồi chiến lược replication xác định node nào chịu trách nhiệm lưu các bản sao.

Điều này **không có nghĩa** dữ liệu của phân vùng chỉ chiếm một đoạn liên tục trong một SSTable: Cassandra dùng memtable và nhiều SSTable; dữ liệu của cùng phân vùng có thể hiện diện trong nhiều tệp, được hợp nhất về mặt logic khi đọc và được tổ chức lại qua compaction.

### Một phân vùng, nhiều chiều kích thước

| Chiều đo | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Số hàng** | Có bao nhiêu clustering key khác nhau trong partition? | 120.000 sự kiện của một thiết bị trong một ngày. |
| **Số cell/giá trị** | Có bao nhiêu giá trị cột được lưu, cập nhật hoặc xóa? | Mỗi sự kiện có 5 cột dữ liệu, một collection nhiều phần tử. |
| **Dung lượng byte** | Tổng lượng dữ liệu và overhead chiếm bao nhiêu? | Payload nhị phân lớn, clustering key, metadata, index và nén. |
| **Tần suất truy cập** | Partition nhận bao nhiêu lần ghi/đọc mỗi giây? | Thiết bị đông người dùng gửi sự kiện liên tục. |
| **Lịch sử cập nhật/xóa** | Có nhiều version/cell hết TTL/tombstone chưa? | Phân vùng có ít hàng còn sống nhưng phải xử lý nhiều tombstone. |

Không có một con số đơn lẻ đại diện đầy đủ cho “độ lớn” và chi phí vận hành của phân vùng.

## 2. Số hàng: độ rộng theo clustering key

Với partition key cố định, **mỗi tổ hợp clustering key** xác định một hàng logic. Nếu số tổ hợp clustering tăng, số hàng trong phân vùng có thể tăng tương ứng.

Trong ví dụ `readings_by_device`:

```text
(device-01, 08:00, id-A)  -> hàng 1
(device-01, 08:00, id-B)  -> hàng 2
(device-01, 08:01, id-A)  -> hàng 3
(device-01, 08:00, id-A)  -> vẫn là hàng 1 (ghi lại cùng primary key)
```

Vì primary key đầy đủ xác định một hàng, gọi `INSERT` nhiều lần với **đúng cùng khóa** không tạo thêm hàng. Ngược lại, nếu mỗi lần gửi dùng `now()`/UUID mới làm thành phần clustering key, số hàng sẽ tăng dù nghiệp vụ đó thực chất chỉ là một sự kiện được retry.

### Ước tính từ tốc độ sự kiện

Giả sử **một thiết bị** phát sinh trung bình 20 bản ghi/giây, đều trong ngày:

```text
Số hàng/phút  = 20 × 60       = 1.200
Số hàng/giờ   = 20 × 3.600    = 72.000
Số hàng/ngày  = 20 × 86.400   = 1.728.000
Số hàng/30 ngày = 1.728.000 × 30 = 51.840.000
```

Nếu khóa chỉ là `device_id`, sau 30 ngày phân vùng có thể chứa **hơn 51 triệu hàng**. Nếu dùng `(device_id, event_day)` làm partition key, mỗi phân vùng ngày có khoảng **1,7 triệu hàng**. Nếu dùng bucket theo giờ, mỗi phân vùng giờ có khoảng **72.000 hàng**.

Số hàng thực tế cần điều chỉnh theo tỷ lệ ghi thành công, dữ liệu trùng khóa, biến động lưu lượng, TTL và chính sách lưu trữ. Số hàng trung bình cũng chưa nói lên **phân vùng lớn nhất** hoặc phân vùng nhận tải cao nhất.

### “Ít hàng” chưa chắc “nhẹ”

Một phân vùng chỉ có 20 hàng vẫn có thể tốn dung lượng nếu mỗi hàng chứa `blob` hàng megabyte. Ngược lại, 100.000 hàng nhỏ có thể chiếm ít byte hơn, nhưng vẫn có overhead clustering và chi phí duyệt/đánh chỉ mục.

Vì vậy **không chọn bucket chỉ theo giới hạn số hàng**.

## 3. “Số cột” trong wide-column cần hiểu thế nào?

Cụm từ *wide-column* có thể gây hiểu lầm rằng một bảng CQL sẽ tự sinh thêm hàng chục nghìn **tên cột schema** cho mỗi phân vùng. Thực tế, các cột được khai báo bằng `CREATE TABLE` là **cấu trúc schema**; độ rộng theo mỗi phân vùng thường đến từ **nhiều hàng clustering và nhiều cell/giá trị dữ liệu**, không phải tự phát sinh vô hạn tên cột mới trong CQL.

Xét:

```sql
CREATE TABLE log_entries_by_service (
    service_id  uuid,
    log_time    timestamp,
    log_id      uuid,
    level       text,
    message     text,
    attributes  map<text, text>,
    PRIMARY KEY (service_id, log_time, log_id)
);
```

Bảng chỉ khai báo một số cột CQL cố định. Tuy nhiên, một phân vùng của `service_id` có thể có hàng trăm nghìn hàng; mỗi hàng lưu nhiều giá trị. Đặc biệt, `attributes` là **non-frozen map**, các phần tử có thể được biểu diễn thành nhiều cell nội bộ; cập nhật/xóa phần tử cũng ảnh hưởng số cell và tombstone.

### Số giá trị không bằng số cột trong schema

Ước lượng sơ bộ:

```text
Số giá trị/cell gần đúng
  ≈ số hàng × số giá trị cột thường được lưu trung bình mỗi hàng
    + số giá trị static chung của phân vùng
    + chi phí biểu diễn collection và các metadata nội bộ
```

Đây chỉ là mô hình để **ước lượng dữ liệu nghiệp vụ**, **không phải công thức đếm cell vật lý chính xác** của SSTable. Giá trị `null`, row marker, cấu trúc của collection, clustering keys, tombstone và phiên bản Cassandra đều ảnh hưởng cách biểu diễn thực.

| Trường hợp | Ảnh hưởng |
| --- | --- |
| Nhiều hàng, ít cột thường | Chi phí key/row và chỉ mục vẫn tăng theo số hàng. |
| Ít hàng, nhiều cột lớn | Dung lượng và mạng có thể lớn dù số hàng nhỏ. |
| `map`, `set`, `list` không `frozen` | Số phần tử/cell và chi phí cập nhật/xóa có thể tăng. |
| `blob`/`text` chứa payload dài | Byte tăng mạnh mà số cột hầu như không đổi. |
| `STATIC` column | Giá trị chung thuộc mức partition, không tạo một bản riêng cho từng clustering row. |
| Nhiều cập nhật/xóa cùng cột | Có thể sinh tombstone/phiên bản lưu trong các SSTable trước compaction. |

**Kết luận quan trọng:** “bảng có 8 cột” không đủ để kết luận phân vùng nhỏ; cần biết **số hàng, số phần tử collection, kích thước từng giá trị và lịch sử ghi/xóa**.

## 4. Ước lượng dung lượng byte của phân vùng

Có thể bắt đầu từ phép tính ước lượng ở mức dữ liệu logic:

\[
B_{\text{partition}} \approx N_{\text{rows}}
  \times B_{\text{row trung bình}}
  + B_{\text{static}}
  + B_{\text{metadata/index}}
\]

Trong đó:

- `N_rows`: số hàng logic trong một phân vùng tại khoảng thời gian quan tâm.
- `B_row trung bình`: trung bình số byte của dữ liệu cột thường cùng clustering key/overhead tính cho mỗi hàng.
- `B_static`: dữ liệu chung theo phân vùng (nếu có static columns).
- `B_metadata/index`: overhead lưu trữ/đánh chỉ mục; phụ thuộc định dạng và cách ghi.

Để lập kế hoạch ban đầu, khi chưa có mẫu dữ liệu thực tế, có thể dùng:

```text
Số hàng dự kiến
    = tốc độ ghi trung bình (hàng/giây)
      × số giây trong bucket
      × tỷ lệ hàng thực sự khác primary key

Dung lượng payload logic
    ≈ số hàng dự kiến × byte trung bình cho một hàng

Dung lượng cần dự phòng
    = payload logic + overhead + hiệu ứng compaction/TTL/tombstone
      ± sai khác do nén (chưa tính số replica)
```

### Ví dụ: cùng số hàng, dung lượng khác nhau

Giả sử một thiết bị có **72.000 sự kiện/giờ**. Với kích thước giá trị trung bình giả định:

| Dữ liệu trung bình mỗi sự kiện | Tổng payload/giờ | Đánh giá |
| --- | ---: | --- |
| 120 byte | 8,64 MB (khoảng 8,24 MiB) | Rất khác với sự kiện lớn dù số hàng giống nhau. |
| 600 byte | 43,2 MB (khoảng 41,2 MiB) | Cần tính tiếp overhead/key/metadata và lượng ghi thực. |
| 2 KiB | 140,6 MiB | Một bucket giờ có thể đáng kể; nên đo thực tế. |
| 16 KiB | Khoảng 1,10 GiB | Payload lớn khiến bucket giờ khó kiểm soát nếu lưu toàn bộ inline. |

Các con số **chỉ tính payload giả định**, chưa phải số byte trên SSTable. Compression có thể giảm dung lượng, nhưng metadata, key lặp trong biểu diễn, index, tombstone và nhiều SSTable có thể làm footprint vật lý khác đáng kể.

Để đổi đơn vị:

- **1 KiB = 1.024 byte**.
- **1 MiB = 1.024 KiB**.
- **1 GiB = 1.024 MiB**.
- **1 MB = 1.000.000 byte**; không nên trộn lẫn MB và MiB khi lập bảng dự báo.

### “Dung lượng của phân vùng” đo ở đâu?

Có ít nhất ba góc nhìn cần tách biệt:

1. **Dữ liệu logic hiện hành**: các hàng và cell còn giá trị theo cách truy vấn nhìn thấy.
2. **Dung lượng biểu diễn trên đĩa của một replica**: chịu ảnh hưởng compression, SSTable, tombstone và compaction.
3. **Dung lượng toàn cluster**: có thêm replica và chi phí vận hành; không thể suy ra chính xác bằng một phép nhân đơn giản.

Ví dụ payload logic của một phân vùng là 40 MiB, keyspace có `replication factor = 3`. Có thể dùng **khoảng 120 MiB dữ liệu logic trên ba bản sao** làm mốc suy nghĩ ban đầu, nhưng dung lượng đĩa thực tế không nhất thiết chính xác 120 MiB vì nén, định dạng dữ liệu, SSTable chưa compact, repair và các cơ chế lưu trữ khác.

## 5. Vấn đề không chỉ là dung lượng: large partition và hot partition

Hai vấn đề cần chẩn đoán riêng:

| Đặc tính | **Large partition** | **Hot partition** |
| --- | --- | --- |
| Bản chất | Một partition key chứa quá nhiều dữ liệu/hàng/cell. | Một partition key nhận tỷ lệ tải đọc hoặc ghi quá cao. |
| Dấu hiệu thường thấy | Đọc slice rộng chậm, nhiều SSTable/cell, compaction và streaming tốn tài nguyên. | Một số replica chịu tải cao, latency tăng dù phân vùng chưa lớn. |
| Nguyên nhân | Không bucket, giữ lịch sử vô hạn, payload lớn. | Khóa phân bố lệch, một tenant/thiết bị cực kỳ “nóng”. |
| Cách xử lý | Bucket theo thời gian/kích thước, TTL hợp lý, chia dữ liệu lớn. | Phân tán khóa/tải có kiểm soát, giới hạn tốc độ, shard phù hợp với cách đọc. |

Một phân vùng 1 MiB có thể rất nóng nếu nhận hàng chục nghìn request/giây. Một phân vùng hàng trăm MiB cũng có thể ít được truy cập nhưng lại gây chi phí trong repair/streaming/compaction hoặc khi có truy vấn quét dài.

### Vì sao phân vùng lớn gây vấn đề?

- **Read amplification:** nhiều SSTable, tombstone và dải clustering lớn có thể buộc replica đọc/ghép nhiều dữ liệu.
- **Độ trễ không ổn định:** đọc một khoảng rất rộng hoặc một partition có rất nhiều cell có thể làm tăng CPU, I/O, memory pressure và thời gian xử lý.
- **Compaction/streaming/repair:** phân vùng lớn làm tăng khối lượng dữ liệu cần di chuyển hoặc xử lý trong các hoạt động nền.
- **Tập trung tải:** mọi hàng trong một phân vùng thuộc cùng tập replica; thêm hàng vào cùng partition key không tự phân tán sang node ngẫu nhiên.
- **Khó thao tác:** xóa hoặc quét cả phân vùng lớn có thể tạo nhiều công việc liên quan tombstone và compaction về sau.

Không có **một ngưỡng số hàng hay MB duy nhất** phù hợp mọi cluster và phiên bản Cassandra. Các hệ thống thường đặt guardrail/cảnh báo theo cấu hình và quy mô thực tế; cần quyết định bằng số liệu đo, đặc tính workload, mục tiêu latency và kiểm thử tải.

## 6. Chia bucket theo thời gian để giới hạn kích thước

Với dữ liệu phát sinh liên tục, cách phổ biến là bổ sung **bucket thời gian** vào partition key.

### Thiết kế dễ phình to

```sql
CREATE TABLE metrics_by_device_all_time (
    tenant_id  text,
    device_id  uuid,
    measured_at timestamp,
    event_id   uuid,
    payload    text,
    PRIMARY KEY ((tenant_id, device_id), measured_at, event_id)
);
```

Partition key `(tenant_id, device_id)` không thay đổi theo thời gian. Nếu một thiết bị ghi liên tục, phân vùng của nó tăng dần.

### Thiết kế có bucket giờ

```sql
CREATE TABLE metrics_by_device_hour (
    tenant_id   text,
    device_id   uuid,
    hour_bucket timestamp,
    measured_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, device_id, hour_bucket),
        measured_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (measured_at DESC, event_id ASC);
```

Quy ước: `hour_bucket` là thời điểm **đầu giờ theo UTC**, chẳng hạn `2026-11-21T08:00:00Z` cho mọi sự kiện từ 08:00 đến trước 09:00 UTC.

```text
(tenant='acme', device=D1, hour=08:00Z)
    08:00:01, event A
    08:00:02, event B
    ...
    08:59:59, event N

(tenant='acme', device=D1, hour=09:00Z)
    09:00:00, event P
    ...
```

Dù cùng thiết bị, hai giờ khác nhau là hai **partition keys khác nhau**. Cùng một giờ, mọi sự kiện thuộc cùng partition key và được sắp theo `measured_at`/`event_id`.

### Đọc một khoảng trong một bucket

```sql
SELECT measured_at, event_id, payload
FROM metrics_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
  AND measured_at >= '2026-11-21T08:15:00Z'
  AND measured_at <  '2026-11-21T08:30:00Z'
LIMIT 200;
```

Cassandra có thể định vị **một phân vùng cụ thể**, rồi đọc slice clustering keys phù hợp. `LIMIT 200` giới hạn số hàng kết quả; nó **không** bảo đảm Cassandra chỉ đọc đúng 200 cell trên đĩa nếu có tombstone hoặc nhiều SSTable.

### Cần bao nhiêu bucket?

Giả sử tải trung bình **20 sự kiện/giây/thiết bị**, mỗi sự kiện khoảng **600 byte payload**:

| Chiều dài bucket | Hàng/bucket | Payload/bucket ước tính |
| --- | ---: | ---: |
| 1 ngày | 1.728.000 | 1.036,8 MB (khoảng 989 MiB) |
| 1 giờ | 72.000 | 43,2 MB (khoảng 41,2 MiB) |
| 10 phút | 12.000 | 7,2 MB (khoảng 6,9 MiB) |
| 1 phút | 1.200 | 0,72 MB (khoảng 0,69 MiB) |

Các mức bucket **không phải khuyến nghị cố định**. Chọn bucket quá dài gây phân vùng lớn; chọn quá ngắn tạo nhiều partition keys, tăng overhead và buộc các truy vấn lịch sử đọc nhiều partition. Cần kiểm tra **phân bố thực tế, tải cao điểm, khoảng truy vấn thường dùng và độ trễ chấp nhận được**.

### Truy vấn nhiều bucket

Nếu người dùng yêu cầu lịch sử từ **08:45 đến 09:15 UTC**, ứng dụng thường phải:

1. Đọc bucket `08:00Z` với khoảng `[08:45, 09:00)`.
2. Đọc bucket `09:00Z` với khoảng `[09:00, 09:15)`.
3. Kết hợp kết quả và sắp theo `measured_at` ở phía ứng dụng khi cần một thứ tự toàn cục.

`CLUSTERING ORDER BY` chỉ cho thứ tự trong **một phân vùng**, không tạo thứ tự tổng thể giữa hai bucket. Với truy vấn lịch sử hàng tháng và bucket phút, số phân vùng đọc có thể rất lớn; khi đó cần cân nhắc bảng tổng hợp hoặc đường truy cập khác.

## 7. Đừng dùng bucket để che một partition key không cân bằng

Thêm ngày/giờ không luôn giải quyết được mọi vấn đề. Một số mẫu khóa dễ tạo tải lệch:

```sql
-- Mọi thiết bị của tenant cùng đi vào một phân vùng theo ngày:
PRIMARY KEY ((tenant_id, event_day), device_id, measured_at)

-- Tất cả khách hàng ở cùng trạng thái gom vào một số rất ít phân vùng:
PRIMARY KEY (status, customer_id)

-- Mỗi sự kiện một phân vùng, mất lợi thế đọc dải thời gian theo thiết bị:
PRIMARY KEY ((tenant_id, device_id, measured_at), event_id)
```

Phương án đầu có thể phù hợp **nếu thực sự cần đọc mọi thiết bị của tenant trong ngày và dữ liệu đủ nhỏ**, nhưng một tenant lớn vẫn có thể tạo phân vùng khổng lồ. Phương án thứ hai có cardinality partition key thấp; phương án thứ ba tạo rất nhiều phân vùng nhỏ và làm truy vấn lịch sử theo thiết bị phức tạp.

Nếu một thiết bị vẫn quá nóng ngay trong bucket ngắn, có thể cân nhắc **shard có kiểm soát**, chẳng hạn thêm `shard_id` vào partition key và xác định quy tắc ghi/đọc nhất quán. Tuy nhiên, **mọi truy vấn lịch sử phải biết hoặc quét các shard liên quan**, nên đánh đổi là nhiều truy vấn nhỏ thay cho một truy vấn partition đơn.

Không chọn số shard ngẫu nhiên mà thiếu thiết kế đọc, retry và tính toán khóa định tuyến.

## 8. TTL, tombstone và dữ liệu đã xóa làm phép đo phức tạp

Giả sử hệ thống chỉ cần giữ bản đo **7 ngày**. Có thể cấu hình TTL cho dữ liệu mới:

```sql
INSERT INTO metrics_by_device_hour (
    tenant_id, device_id, hour_bucket, measured_at, event_id, payload
) VALUES (
    'acme',
    327a71e9-f562-4b54-94b9-2138a9e30b12,
    '2026-11-21T08:00:00Z',
    '2026-11-21T08:15:00Z',
    8817a208-1858-4144-86e9-b24d9083e478,
    'temperature=37.9'
) USING TTL 604800;
```

TTL `604800` tương đương **7 ngày tính bằng giây**. Khi hết hạn, dữ liệu không còn được xem là giá trị sống cho truy vấn bình thường; nhưng tombstone và các thành phần lưu trữ liên quan vẫn có thể tồn tại trên đĩa cho đến khi đủ điều kiện dọn dẹp trong quy trình compaction.

Điều cần tách biệt:

- **Số hàng còn sống:** hàng mà ứng dụng còn đọc được.
- **Số tombstone:** dấu xóa hoặc hết hạn; có thể làm truy vấn tốn công ngay cả khi trả rất ít hàng.
- **Dung lượng SSTable hiện tại:** có thể phản ánh dữ liệu cũ/chưa compact, không bằng phép nhân đơn giản số hàng đang sống × số byte/hàng.
- **TTL trên từng cell:** nếu một số cột sống lâu hơn cột khác, hàng và partition có thể còn lại dữ liệu dù nhiều giá trị đã hết hạn.

TTL **không thay thế** việc chọn partition key tốt. Nếu một partition nhận khối lượng dữ liệu khổng lồ mỗi giờ, nó vẫn có thể nóng và gây chi phí xử lý trước khi TTL có tác dụng.

Các thao tác xóa dữ liệu hàng loạt hoặc sửa đi sửa lại nhiều cột trong một phân vùng cũng có thể làm tăng tombstone. Khi đánh giá vấn đề hiệu năng, cần xem cả **kích thước phân vùng và lịch sử cập nhật/xóa**.

## 9. Theo dõi kích thước phân vùng trong thực tế

Cassandra cung cấp số liệu ở nhiều mức: bảng, SSTable và truy vấn. Tên lệnh/trường thống kê có thể khác nhau theo phiên bản, vì vậy cần đối chiếu với phiên bản đang vận hành.

### Thống kê và phân bố ở mức bảng

Ví dụ các lệnh quản trị thường dùng:

```bash
# Thông tin bảng, gồm thống kê kích thước partition đã compact:
nodetool tablestats my_keyspace.metrics_by_device_hour

# Histogram kích thước partition/cell count và một số độ trễ:
nodetool tablehistograms my_keyspace metrics_by_device_hour
```

Khi xem kết quả, tập trung vào:

- **Compacted partition minimum/mean/maximum bytes** (nếu phiên bản cung cấp): giúp phát hiện mức phân tán kích thước và outlier, nhưng là thống kê/ước lượng, không phải số byte chính xác tức thời của mọi phân vùng đang sống.
- **Partition size histogram**: xác định phần đuôi phân phối; nếu phần lớn partition nhỏ nhưng một số rất lớn, giá trị trung bình có thể che giấu rủi ro.
- **Cell count histogram**: cho thấy phân bố số cell/giá trị biểu diễn trong partition theo cách công cụ thống kê của phiên bản đó.
- **Read/write latency, SSTables per read, tombstones scanned, cảnh báo large partition**: dùng để nối số liệu kích thước với tác động lên truy vấn và I/O.

Không nên khẳng định từ một kết quả `tablestats` rằng **mọi partition** đều có kích thước bằng con số trung bình. Thống kê có thể được thu thập theo lịch compaction/SSTable và thay đổi theo phiên bản, compression và tình trạng lưu trữ.

### Phân tích nguyên nhân ở mức partition key

Nếu đã biết một partition key đang có dấu hiệu bất thường, hãy điều tra theo khóa đó với các truy vấn **giới hạn rõ ràng** và quan sát thời gian phản hồi. Ví dụ:

```sql
SELECT measured_at, event_id, payload
FROM metrics_by_device_hour
WHERE tenant_id = 'acme'
  AND device_id = 327a71e9-f562-4b54-94b9-2138a9e30b12
  AND hour_bucket = '2026-11-21T08:00:00Z'
LIMIT 20;
```

Kết quả 20 hàng **không có nghĩa** phân vùng chỉ có 20 hàng. Đây là cách kiểm tra đường truy cập, không phải phép đo kích thước toàn partition.

Cũng không nên coi `SELECT COUNT(*)` trên một partition khổng lồ hoặc toàn bảng là phép đo miễn phí: Cassandra cần xử lý các hàng/cell liên quan để đếm, có thể gây tải lớn. Đối với dữ liệu sản xuất, nên ưu tiên histogram, metrics, log/cảnh báo và mẫu đo có kiểm soát.

### Kiểm tra số liệu từ nhiều replica

Vì Cassandra có replication, node khác nhau có thể có trạng thái SSTable/compaction khác nhau. Khi chẩn đoán hotspot hoặc partition rất lớn, nên so sánh số liệu của **các node giữ replica liên quan**, đồng thời đánh giá consistency, compaction và repair nếu xuất hiện chênh lệch bất thường.

Không cộng dung lượng được báo bởi mỗi node rồi xem đó là “kích thước logic của một partition”: có thể đã tính cả replica, tệp chưa compact và các khoản overhead khác nhau.

## 10. Đọc có giới hạn từ ứng dụng Java

Giả sử ứng dụng Java cần hiển thị tối đa 200 bản đo của một thiết bị trong một bucket giờ. Java Driver 4.x cho phép sử dụng **prepared statement** và **page size** thay vì tải vô hạn dữ liệu vào bộ nhớ ứng dụng.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

public final class MetricsRepository {
    private final CqlSession session;
    private final PreparedStatement findReadings;

    public MetricsRepository(CqlSession session) {
        this.session = session;
        this.findReadings = session.prepare(
            "SELECT measured_at, event_id, payload " +
            "FROM metrics_by_device_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND measured_at >= ? AND measured_at < ? " +
            "LIMIT 200"
        );
    }

    public ResultSet readInHour(
            String tenantId,
            UUID deviceId,
            Instant sampleTimestamp,
            Instant fromInclusive,
            Instant toExclusive) {

        // Instant được hiểu theo UTC; bucket là đầu giờ UTC.
        Instant hourBucket = sampleTimestamp.truncatedTo(ChronoUnit.HOURS);

        BoundStatement statement = findReadings.bind(
            tenantId, deviceId, hourBucket, fromInclusive, toExclusive
        ).setPageSize(100);

        return session.execute(statement);
    }
}
```

Khi dùng phương thức này:

- `hourBucket` phải trùng **chính xác cách producer tính bucket** lúc ghi dữ liệu.
- `fromInclusive` và `toExclusive` nên nằm trong giờ/bucket được chọn. Nếu trải qua nhiều giờ, ứng dụng cần tách truy vấn theo bucket; nếu không, dữ liệu ở bucket khác sẽ bị bỏ sót.
- `LIMIT 200` giới hạn tối đa số hàng kết quả; `setPageSize(100)` là số hàng mong muốn trong mỗi trang driver. Chúng có ý nghĩa khác nhau.
- Không nên gọi `all()` và giữ toàn bộ kết quả lớn trong RAM khi người dùng chỉ cần một trang. Hãy dùng paging state hoặc xử lý từng trang cho những truy vấn dài.
- Giới hạn kết quả và paging **không làm phân vùng nhỏ đi**; schema và chiến lược bucket mới quyết định độ lớn của dữ liệu lưu theo khóa.

Nếu ứng dụng phục vụ dashboard có truy vấn “toàn bộ thiết bị trong một tenant theo thời gian”, bảng `metrics_by_device_hour` không trực tiếp cung cấp thứ tự toàn cục. Có thể cần bảng tổng hợp chuyên dụng hoặc một quy trình truy vấn khác.

## 11. Quy trình thiết kế và giám sát phân vùng

Khi tạo bảng mới, có thể đi theo trình tự:

1. **Xác định truy vấn chính:** ví dụ “đọc 100 sự kiện gần nhất của thiết bị trong một giờ”, “đọc 30 ngày lịch sử”, “tổng hợp trung bình nhiệt độ theo ngày”.
2. **Chọn thực thể tạo partition key:** tenant, user, device, account… sao cho ứng dụng biết đủ thành phần khóa khi đọc.
3. **Ước lượng số hàng:** tốc độ trung bình và đỉnh, độ dài bucket, tỷ lệ hàng mới so với upsert.
4. **Ước lượng byte:** lấy mẫu payload và phân phối kích thước, tính chi phí clustering/regular columns, collection và metadata; phân biệt payload logic với byte SSTable.
5. **Xác định tải/tần suất đọc:** tránh tổ hợp khóa nhận quá nhiều request ngay cả khi dung lượng chưa cao.
6. **Chọn bucket và kiểm tra chi phí truy vấn:** ngày/giờ/phút hoặc shard có kiểm soát; tính số partition phải đọc cho truy vấn thường xuyên.
7. **Chính sách vòng đời:** TTL, xóa, tombstone, compaction, lưu trữ dài hạn và cách xác định bucket khi retry.
8. **Thử tải và quan sát:** histogram partition size, cell count, latency, số tombstone, partition lớn nhất và replica bị nóng; điều chỉnh bằng dữ liệu thực.

### Bảng chẩn đoán nhanh

| Dấu hiệu | Phân tích đầu tiên | Hướng xử lý |
| --- | --- | --- |
| Một số partition rất lớn, trung bình bảng vẫn thấp | Phân bố kích thước lệch, một số key có nhiều hàng/payload | Xác định key nóng/lớn, bucket hoặc chia bảng theo truy vấn. |
| Kích thước nhỏ nhưng ghi chậm trên một số node | Hot partition hoặc tập replica nhận tải tập trung | Kiểm tra lưu lượng theo key, shard/throttling, phân phối workload. |
| Ít hàng trả về nhưng đọc rất chậm | Tombstone, nhiều SSTable, slice rộng | Điều tra tombstones/compaction, thu hẹp khoảng đọc. |
| Dung lượng đĩa lớn hơn nhiều so với dữ liệu đang sống | Replica, compression, tombstone, SSTable chưa compact | Tách logic size và physical size; kiểm tra compaction/TTL. |
| Truy vấn nhiều tháng phải gọi hàng nghìn bucket | Bucket quá nhỏ so với truy vấn chủ lực | Dùng bucket/bảng tổng hợp phù hợp, cân nhắc thay đổi đường truy cập. |
| `LIMIT 100` vẫn có cảnh báo large partition | `LIMIT` chỉ giới hạn kết quả | Thiết kế lại khóa hoặc chính sách vòng đời phân vùng. |
| Thêm cột thường nhỏ không cải thiện độ trễ | Gốc vấn đề nằm ở phân bố/tombstone/I/O | Dùng số liệu read latency, disk và per-key để xác định nguyên nhân. |

## 12. Bài tập thực hành

Một ứng dụng ghi lịch sử thao tác của khách hàng, gồm:

- 1.000 khách hàng hoạt động.
- Mỗi khách hàng trung bình **10 sự kiện/giây** trong giờ cao điểm, kéo dài 2 giờ mỗi ngày.
- Payload logic trung bình mỗi sự kiện **1 KiB**, chưa tính overhead.
- Nhu cầu đọc chính: “lấy tối đa 100 sự kiện mới nhất của **một khách hàng trong một ngày**”.
- Nhu cầu đọc phụ: “xem lịch sử **7 ngày** của khách hàng đó”.

Xét hai phương án:

```sql
-- Phương án A: một phân vùng cho mọi lịch sử của khách hàng.
PRIMARY KEY (customer_id, occurred_at, event_id)

-- Phương án B: mỗi ngày của khách hàng là một phân vùng.
PRIMARY KEY ((customer_id, event_day), occurred_at, event_id)
```

**Câu hỏi:**

1. Trong 2 giờ cao điểm, một khách hàng phát sinh khoảng bao nhiêu hàng?
2. Payload logic của số hàng trên khoảng bao nhiêu MiB?
3. Sau 30 ngày cùng lưu lượng, kích thước payload cộng dồn của phương án A là bao nhiêu, nếu không TTL và không ghi trùng khóa?
4. Phương án B có giúp giới hạn số hàng theo partition key tốt hơn A không?
5. Truy vấn lịch sử 7 ngày của B sẽ cần làm gì?
6. Nếu một khách hàng đột biến lên **200 sự kiện/giây**, bucket ngày có chắc đủ an toàn không?
7. Có nên dùng `SELECT COUNT(*)` trên mọi khách hàng trong giờ cao điểm để giám sát số hàng không?

**Đáp án và giải thích:**

1. `10 × 3.600 × 2 = 72.000` hàng/khách hàng/ngày.
2. `72.000 KiB / 1.024 ≈ 70,3 MiB` payload/ngày.
3. `70,3125 MiB × 30 ≈ 2.109,4 MiB ≈ 2,06 GiB` payload cho một partition A trong 30 ngày (chưa overhead/compaction).
4. **Có**: B tạo phân vùng mới mỗi ngày. Số hàng trong một partition ngày khoảng 72.000 theo giả định; A cộng dồn toàn lịch sử.
5. Phải đọc **7 bucket ngày** phù hợp và hợp nhất/sắp xếp theo thời gian nếu muốn một danh sách chung; không có thứ tự clustering toàn cục giữa các phân vùng.
6. **Không chắc**: `200 × 3.600 × 2 = 1.440.000` hàng trong 2 giờ, khoảng **1,37 GiB payload/ngày** ở mức 1 KiB/hàng. Cần đánh giá bucket giờ/phút hoặc chia tải, dựa trên truy vấn và số liệu thực tế.
7. **Không**: phép đếm khổng lồ trong giờ cao điểm có thể gây tải đáng kể. Dùng metrics/histogram, thống kê chủ động từ luồng ghi và sampling có kiểm soát.

Bài tập minh họa vì sao **số hàng**, **số byte** và **tần suất truy cập** đều phải được xét; chỉ biết tên partition key hoặc số cột của schema chưa đủ.

## 13. Ghi nhớ

- Một **partition** là nhóm dữ liệu ứng với **toàn bộ partition key**; có thể chứa rất nhiều hàng clustering.
- Đánh giá kích thước theo **số hàng**, **số cell/giá trị**, **số byte**, **tombstone** và **tải truy cập**; số lượng cột CQL trong schema chỉ là một phần câu chuyện.
- Dung lượng logic, dung lượng trên SSTable của replica và dung lượng toàn cluster **không phải cùng một chỉ số**.
- **Large partition** liên quan kích thước dữ liệu; **hot partition** liên quan độ tập trung lưu lượng. Có thể gặp một hoặc cả hai.
- **Time bucketing** giúp giới hạn lịch sử tích lũy trong một partition, nhưng tăng số partition phải truy vấn khi đọc nhiều bucket.
- `LIMIT`, driver paging và TTL giúp kiểm soát kết quả/vòng đời dữ liệu; chúng **không thay thế** việc chọn partition key hợp lý.
- Quan sát histogram, outlier, tombstone, compaction và hiệu năng replica trước khi quyết định bucket theo ngày, giờ hay phút.

Khi hiểu rõ số hàng, số cột/cell và dung lượng, bạn có thể thiết kế Cassandra có phân vùng dự đoán được, vận hành replication/compaction/repair với ít bất ngờ hơn, và xây dựng truy vấn CQL cùng ứng dụng Java đáp ứng yêu cầu độ trễ thực tế.

