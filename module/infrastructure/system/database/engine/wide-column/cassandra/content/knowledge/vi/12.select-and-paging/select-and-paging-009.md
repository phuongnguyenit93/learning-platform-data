# ALLOW FILTERING và đánh giá lượng dữ liệu phải quét trong Apache Cassandra

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao Apache Cassandra ưu tiên truy vấn xác định **partition key** và **clustering range** thay vì lọc tự do trên các cột thường.
2. Hiểu `ALLOW FILTERING` là sự chấp nhận một kiểu thực thi có thể phải đọc nhiều dữ liệu rồi mới lọc, **không phải cơ chế tạo chỉ mục hoặc bảo đảm hiệu năng**.
3. Phân biệt ba đại lượng: **số partition cần xét**, **số dòng ứng viên phải kiểm tra** và **số dòng trả về**.
4. Ước lượng tỉ lệ dòng khớp, fan-out, read amplification, tác động của `LIMIT`, `PER PARTITION LIMIT`, TTL và tombstone.
5. Dùng `TRACING`, metrics và thử nghiệm tải để đánh giá thực tế thay vì dựa vào số dòng kết quả.
6. Chọn giữa lọc có giới hạn, bảng thiết kế theo truy vấn, chỉ mục phù hợp (ví dụ SAI trong Cassandra hỗ trợ) và bảng tổng hợp.
7. Viết truy vấn tham số hóa với Java Driver, đặt ranh giới an toàn và phân biệt lỗi CQL với vấn đề tải/replica.

Đây là bài trong chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Mô-đun nghiên cứu kiến trúc phân tán và mô hình wide-column của Apache Cassandra: từ partition key, thiết kế bảng theo truy vấn, consistency đọc ghi đến CQL, replication, compaction, repair, xử lý lỗi và kết nối ứng dụng Java. Chủ đề ở đây tập trung vào một câu hỏi vận hành: **một truy vấn trả vài dòng có thể đã bắt Cassandra đọc bao nhiêu dữ liệu?**

## 1. Cassandra định vị dữ liệu trước khi lọc như thế nào?

Xét bảng có khóa chính:

```sql
PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
```

| Thành phần | Vai trò | Tác động đến `WHERE` |
| --- | --- | --- |
| `tenant_id` và `event_day` | **Composite partition key** | Cả cặp cùng xác định partition và token dùng để tìm replica. |
| `occurred_at` | Clustering column đầu tiên | Chọn một thời điểm hoặc khoảng liên tiếp **trong partition**. |
| `event_id` | Clustering column thứ hai | Phân biệt các dòng có cùng thời điểm, hỗ trợ ranh giới khóa đầy đủ. |
| `event_type`, `device` | Regular columns | Không tự tạo đường định vị theo riêng các giá trị này. |

Hình dung đường đọc:

```text
Truy vấn từ ứng dụng
       |
       v
WHERE: có đủ (tenant_id, event_day)?
       |
       +-- Có --> tính token --> định vị partition/replica
       |                            |
       |                            v
       |                   clustering key/range
       |                            |
       |                            v
       |                 các dòng ứng viên trong partition
       |                            |
       |                            v
       |                 kiểm tra điều kiện cột thường
       |                            |
       |                            v
       |                       dòng kết quả
       |
       +-- Không --> không có đường đọc theo partition đầy đủ;
                     có thể bị từ chối hoặc phải quét rộng
                     nếu loại truy vấn và cấu hình cho phép
```

Hai đường đọc đầu không giống nhau:

- **Đọc theo khóa:** `WHERE tenant_id = ... AND event_day = ... AND occurred_at >= ...` giúp xác định đúng partition và dải clustering.
- **Đọc rồi lọc:** thêm `AND event_type = 'VIEW'` khi `event_type` chỉ là cột thường có thể buộc Cassandra kiểm tra từng dòng ứng viên để biết nó có khớp hay không.

Một partition được xác định rõ có thể chứa ít dòng hoặc hàng triệu dòng. Vì vậy **đủ partition key** là điều kiện rất có ích nhưng **chưa đủ** để khẳng định một truy vấn lọc cột thường luôn rẻ.

## 2. ALLOW FILTERING thực sự làm gì?

Ví dụ một câu truy vấn thông thường:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW';
```

Nếu bảng chưa có chỉ mục hay cách truy cập nào phù hợp cho `event_type`, Cassandra thường từ chối câu này với thông báo đại ý rằng truy vấn có thể cần lọc dữ liệu và chỉ thực thi khi cho phép filtering.

Thêm:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

Nghĩa của `ALLOW FILTERING` là: **người viết truy vấn chấp nhận khả năng Cassandra phải xử lý một tập dữ liệu lớn hơn tập kết quả để đánh giá điều kiện**.

Điều đó **không** có nghĩa:

- Tạo secondary index, Storage-Attached Index (SAI) hay một cột clustering mới.
- Thay đổi partition key hoặc gom các partition có cùng giá trị regular column.
- Bảo đảm chi phí chỉ tỉ lệ với số dòng trả về.
- Bảo đảm truy vấn được hỗ trợ trong mọi cấu hình: một số hình dạng `WHERE` vẫn bị từ chối hoặc bị guardrail/chính sách giới hạn.
- Biến `LIMIT 1` thành phép tra cứu một dòng theo khóa.

**Phân biệt lỗi và quyết định thiết kế:** “truy vấn chạy được với `ALLOW FILTERING`” chỉ xác nhận CQL đã cho phép kế hoạch đọc đó, **không** chứng minh truy vấn đạt mục tiêu p95/p99 của API.

## 3. Lab CQL: ba partition, mười dòng

Để quan sát cụ thể, xây một bảng log cho các hoạt động của tenant theo ngày.

### 3.1. Tạo keyspace và bảng

```sql
-- Chỉ dùng SimpleStrategy / RF=1 cho bài lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_filter_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_filter_lab;

CREATE TABLE IF NOT EXISTS events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    device text,
    detail text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

Mỗi `(tenant_id, event_day)` là một partition. Trong partition, các sự kiện sắp theo `occurred_at` rồi `event_id` tăng dần. Hai cột `event_type` và `device` **không** thuộc khóa.

### 3.2. Nạp dữ liệu

```sql
-- Tenant A, ngày 20/11: 5 dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000011,
    'LOGIN', 'web', 'Dang nhap'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000012,
    'VIEW', 'web', 'Xem don hang'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000013,
    'VIEW', 'mobile', 'Xem tren dien thoai'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000014,
    'CLICK', 'mobile', 'Mo chi tiet'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-20',
    '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000015,
    'LOGOUT', 'web', 'Dang xuat'
);

-- Tenant A, ngày 21/11: 3 dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-21',
    '2026-11-21 07:00:00+0000',
    00000000-0000-4000-8000-000000000021,
    'LOGIN', 'mobile', 'Dang nhap ngay 21'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-21',
    '2026-11-21 08:00:00+0000',
    00000000-0000-4000-8000-000000000022,
    'VIEW', 'mobile', 'Xem san pham'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    11111111-1111-4111-8111-111111111111, '2026-11-21',
    '2026-11-21 09:00:00+0000',
    00000000-0000-4000-8000-000000000023,
    'CLICK', 'web', 'Bam mua hang'
);

-- Tenant B, ngày 20/11: 2 dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    22222222-2222-4222-8222-222222222222, '2026-11-20',
    '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000031,
    'LOGIN', 'web', 'Dang nhap B'
);

INSERT INTO events_by_tenant_day
    (tenant_id, event_day, occurred_at, event_id, event_type, device, detail)
VALUES (
    22222222-2222-4222-8222-222222222222, '2026-11-20',
    '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000032,
    'VIEW', 'mobile', 'Xem san pham B'
);
```

Tổng hợp từ dữ liệu lab:

| Partition key | Số dòng | Số `VIEW` | Số `mobile` |
| --- | ---: | ---: | ---: |
| (Tenant A, 20/11) | 5 | 2 | 2 |
| (Tenant A, 21/11) | 3 | 1 | 2 |
| (Tenant B, 20/11) | 2 | 1 | 1 |
| **Toàn bảng lab** | **10** | **4** | **5** |

Những con số này giả định bảng vừa được tạo và chỉ có dữ liệu mẫu, chưa có TTL, delete hay ghi khác. Chạy lại `INSERT` với cùng primary key là upsert, không thêm dòng trùng.

## 4. Cùng một yêu cầu, ba phạm vi truy vấn

### 4.1. Theo khóa: đọc một partition đã biết

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';
```

Kết quả có **5 dòng**. Cặp `(tenant_id, event_day)` hoàn chỉnh giúp Cassandra định vị đúng **một partition**. Không cần `ALLOW FILTERING` vì không có điều kiện yêu cầu lọc thêm một regular column.

Nhưng trong thực tế, năm dòng có thể trở thành hàng triệu dòng nếu tenant ghi dữ liệu dày đặc trong một ngày. Thiết kế bucket “một ngày” phải gắn với lưu lượng và kích thước partition, không chỉ với tên `event_day`.

### 4.2. Theo khóa rồi lọc regular column trong một partition

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

Kết quả từ dữ liệu mẫu: **2 dòng** lúc `09:00` và `10:00`. Nhưng để biết hai dòng này khớp `VIEW`, Cassandra có thể cần kiểm tra các dòng của partition ngày 20.

Mô hình đơn giản khi không có index:

```text
Partition (Tenant A, 20/11)

08:00 LOGIN  -- không khớp
09:00 VIEW   -- khớp
10:00 VIEW   -- khớp
11:00 CLICK  -- không khớp
12:00 LOGOUT -- không khớp

Tập ứng viên: 5 dòng
Tập kết quả:  2 dòng
Tỷ lệ khớp:  2 / 5 = 40%
```

Ở đây `5` là kích thước **tập ứng viên logic** trong lab, không phải khẳng định storage engine luôn đọc đúng năm record vật lý hoặc năm disk blocks. Kế hoạch thực thi, cache và giới hạn có thể thay đổi công việc thực tế; TTL/tombstone có thể làm số mục cần xử lý **nhiều hơn** số dòng sống.

### 4.3. Thu hẹp bằng clustering range trước khi lọc

```sql
SELECT occurred_at, event_id, event_type, device
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
  AND device = 'mobile'
ALLOW FILTERING;
```

Lúc này, partition vẫn chỉ có **một**, nhưng khoảng clustering `[09:00, 12:00)` chỉ gồm **3 dòng ứng viên**:

| Giờ UTC | `event_type` | `device` | Có khớp? |
| --- | --- | --- | --- |
| 09:00 | `VIEW` | `web` | Không |
| 10:00 | `VIEW` | `mobile` | Có |
| 11:00 | `CLICK` | `mobile` | Có |

Kết quả là **2 dòng**. Tỷ lệ khớp của tập ứng viên đã thu hẹp là `2/3 ≈ 66,7%`.

**Bài học:** Nếu buộc phải lọc regular column, hãy cố gắng dùng **partition key đầy đủ** và **clustering range ngắn** để hạn chế dữ liệu cần kiểm tra. Điều đó thường tốt hơn một truy vấn lọc regular column trên cả partition lớn, nhưng phải benchmark với kích thước và phân bố dữ liệu thực.

## 5. Truy vấn thiếu khóa: quét nhiều partition

### 5.1. Lọc một regular column mà không có partition key

```sql
-- Ví dụ rủi ro: không có khóa định vị partition.
-- Chỉ nên thử trên lab nhỏ nếu cluster cho phép.
SELECT tenant_id, event_day, occurred_at, event_type
FROM events_by_tenant_day
WHERE event_type = 'VIEW'
ALLOW FILTERING;
```

Với dữ liệu mẫu, có **4 dòng `VIEW` từ 3 partition**. Nhưng vì `event_type` là regular column và bảng không có index phù hợp, Cassandra không thể tự suy ra những partition chứa `VIEW`. Trong trường hợp câu lệnh được phép thực thi, nó có thể cần quét dữ liệu trên **nhiều token range và replica**.

Ở production, một bảng có hàng triệu partition sẽ khác hoàn toàn lab chỉ ba partition. Truy vấn có thể thất bại do giới hạn, timeout hoặc tạo tải nghiêm trọng trước khi tìm hết kết quả.

### 5.2. Composite partition key phải đủ thành phần

```sql
-- Không định vị được partition đầy đủ:
SELECT event_day, occurred_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111;
```

Vì partition key là **`(tenant_id, event_day)`**, biết `tenant_id` không khiến Cassandra có một index liệt kê tự động mọi ngày của tenant. Thêm `ALLOW FILTERING` không phải cách giải quyết ổn định cho API phải truy vấn lịch sử nhiều ngày.

Khi cần nhiều ngày cụ thể, có thể liệt kê những bucket đã biết bằng `IN` trên thành phần cuối của composite partition key:

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21');
```

Truy vấn trên chọn **2 partition ứng viên**, không yêu cầu lọc regular column. Nếu lại thêm `AND event_type = 'VIEW' ALLOW FILTERING`, nó có thể phải kiểm tra các dòng trong **cả hai partition**. Với lab: `5 + 3 = 8` dòng ứng viên và `2 + 1 = 3` dòng `VIEW` khớp.

**Lưu ý:** `ALLOW FILTERING` không phải giấy phép bỏ qua mọi quy tắc CQL về composite partition key hay clustering columns. Một số tổ hợp điều kiện vẫn bị từ chối tùy phiên bản và cấu hình. Khi đó cần thay đổi điều kiện truy vấn, chỉ mục hoặc mô hình bảng chứ không chỉ thêm từ khóa này.

## 6. Ước lượng lượng dữ liệu phải quét

### 6.1. Mô hình đếm ứng viên theo partition

Giả sử một request xác định tập `K` gồm `P` **full partition keys**. Trong partition `i`, sau các điều kiện clustering range, có `N_i` dòng logic ứng viên. Trong số đó, `M_i` dòng khớp các điều kiện regular column.

```text
P = số full partition-key candidates
N = N_1 + N_2 + ... + N_P  (dòng ứng viên logic)
M = M_1 + M_2 + ... + M_P  (dòng khớp điều kiện lọc)

Match rate = M / N, nếu N > 0
Candidate-to-result ratio = N / M, nếu M > 0
```

Ví dụ:

| Truy vấn | `P` | `N` | `M` | Tỷ lệ khớp |
| --- | ---: | ---: | ---: | ---: |
| Tenant A/ngày 20, lọc `event_type = VIEW` | 1 | 5 | 2 | 40% |
| Tenant A/ngày 20, khoảng 09–12, lọc `device = mobile` | 1 | 3 | 2 | 66,7% |
| Tenant A/ngày 20–21, lọc `event_type = VIEW` | 2 | 8 | 3 | 37,5% |
| Toàn bảng lab, lọc `event_type = VIEW` | 3 | 10 | 4 | 40% |

Đây là mô hình **số lượng logic để ước lượng**, không phải chi phí chính xác:

- Một cột có giá trị hiếm làm `M` nhỏ, nhưng **không** tự làm `N` nhỏ khi không có index.
- Partition lớn với `N` lớn vẫn có thể chậm dù `M = 1`.
- Tập dữ liệu không tồn tại hoặc tất cả dòng không khớp có `M = 0`, nhưng hệ thống vẫn có thể phải làm việc đáng kể để xác minh.
- Nếu dùng `LIMIT`, truy vấn có thể **dừng sớm**, khiến số dòng thực tế được xem nhỏ hơn `N`. Không vì thế mà có bảo đảm về số mục phải đọc trong trường hợp xấu nhất.

### 6.2. Tính cả kích thước dòng và chi phí khác

Đánh giá sơ bộ có thể kết hợp:

```text
Candidate bytes (ước lượng thô)
  ≈ tổng số dòng logic cần xét × kích thước dữ liệu trung bình cần đọc

Read work thực tế
  = candidate reads
  + memtable/SSTable lookup và reconciliation
  + tombstone/TTL handling
  + replica/network/coordinator overhead
```

Không coi biểu thức trên là công thức nội bộ chính thức của Cassandra. Kích thước dòng không đồng đều, bộ nhớ đệm, compression, SSTable layout, index và cơ chế đọc thực tế khiến số bytes vật lý khác nhiều ước lượng thô.

### 6.3. Phân biệt độ chọn lọc và fan-out

Hai câu hỏi độc lập:

1. **Fan-out:** Có bao nhiêu partition/token range/replica cần liên quan để tìm dữ liệu?
2. **Tỷ lệ khớp:** Trong dữ liệu đã phải xem, bao nhiêu dòng đáp ứng điều kiện regular column?

Ví dụ, `IN` gồm 100 ngày sẽ định danh tới 100 partition ứng viên của một tenant. Nếu mỗi partition có 10.000 sự kiện, lọc một `event_type` hiếm có thể trả vài chục dòng nhưng vẫn đòi xử lý lượng ứng viên lớn. Một chỉ mục tốt hoặc một bảng thiết kế theo loại sự kiện có thể thay đổi đường truy cập; chỉ thêm `LIMIT` thì không.

## 7. LIMIT, PER PARTITION LIMIT và page size không phải chỉ mục

### 7.1. LIMIT 1 có thể phải kiểm tra nhiều dòng

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'LOGOUT'
LIMIT 1
ALLOW FILTERING;
```

Với lab, chỉ một dòng `LOGOUT` nằm **cuối** partition theo thứ tự `occurred_at ASC`: lúc 12:00. Một cách thực thi phải xem xét các ứng viên trước khi tìm thấy dòng khớp; `LIMIT 1` chỉ giới hạn kết quả còn một dòng, **không tạo đường truy cập trực tiếp tới `event_type = LOGOUT`**.

Nếu có hàng trăm nghìn dòng không khớp trước một dòng khớp, việc lấy **một dòng** vẫn có thể rất đắt. Nếu không có dòng nào khớp, công việc xác minh kết quả rỗng cũng có thể lớn.

### 7.2. PER PARTITION LIMIT giới hạn output theo partition

```sql
SELECT event_day, occurred_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 1;
```

Truy vấn này **không cần `ALLOW FILTERING`** vì nó chỉ dùng partition key và giới hạn số dòng lấy từ mỗi partition. Nó có thể trả hai dòng, một từ ngày 20 và một từ ngày 21, theo clustering order của mỗi partition.

Nếu thêm điều kiện lọc regular column với `ALLOW FILTERING`, mỗi partition có thể phải kiểm tra nhiều ứng viên mới tìm ra dòng được giữ. `PER PARTITION LIMIT 1` không bảo đảm Cassandra chỉ đọc một dòng vật lý hoặc chỉ định vị một partition.

### 7.3. Page size là cách tải kết quả, không phải phạm vi quét

Java driver có `setPageSize(n)` và paging state. Chúng dùng để lấy kết quả thành các đợt, nhưng:

| Cơ chế | Mục đích | Có tạo đường truy cập cho `event_type`? |
| --- | --- | --- |
| Full partition key trong `WHERE` | Định vị partition | Không, nhưng thu hẹp phạm vi. |
| Clustering range | Thu hẹp dải dòng trong partition | Không, nhưng thu hẹp phạm vi. |
| `ALLOW FILTERING` | Cho phép một số dạng đọc rồi sàng lọc | **Không**. |
| `LIMIT n` | Giới hạn tổng số dòng kết quả | **Không**. |
| `PER PARTITION LIMIT n` | Giới hạn dòng kết quả mỗi partition | **Không**. |
| Driver page size | Điều tiết số dòng fetch trong một đợt | **Không**. |
| Index phù hợp | Có thể tạo đường truy cập theo cột được lập chỉ mục | **Có thể**, tùy index/phiên bản/câu truy vấn. |

Đừng dùng page size để “chữa” một truy vấn toàn bảng cần lọc `event_type`. Mỗi lần fetch vẫn thuộc cùng kế hoạch truy vấn và vẫn phải thực hiện công việc cần thiết để tìm các dòng khớp.

## 8. Tombstone, TTL, compaction và consistency ảnh hưởng thế nào?

### 8.1. Tombstone và TTL

Trong Cassandra, xóa và hết hạn TTL liên quan đến cơ chế tombstone. Một truy vấn có thể phải đọc và đối chiếu nhiều mảnh dữ liệu để biết dòng nào **còn sống**:

```text
10.000 row versions / cells vật lý (minh họa)
       |
       +-- một phần đã bị xóa hoặc hết TTL
       +-- một phần nằm trong nhiều SSTable
       |
       v
2.000 dòng logic còn sống trong khoảng khóa
       |
       +-- lọc event_type
       v
10 dòng kết quả
```

Các số trong sơ đồ chỉ là giả định minh họa. Điều quan trọng: `M = 10` **không** cho biết có bao nhiêu tombstone/cell/SSTable phải xử lý. Khi số dòng hợp lệ thấp nhưng nhiều dữ liệu đã hết hạn, `LIMIT 10` vẫn có thể dẫn đến truy vấn chậm hoặc cảnh báo tombstone.

Compaction giúp tổ chức SSTable và dọn các dữ liệu không còn cần thiết theo những điều kiện an toàn; repair giúp replica hội tụ. Không thể coi compaction/repair là “cách làm `ALLOW FILTERING` rẻ” cho mọi truy vấn, bởi đường truy cập vẫn không thay đổi.

### 8.2. Replication và consistency

Giả sử replication factor là 3 trong cùng chiến lược topology phù hợp. Điều đó **không** có nghĩa một truy vấn lọc ba partition phải trả số dòng nhân ba: replicas là các bản sao của dữ liệu logic. Tuy nhiên số replica cần phản hồi, sự chênh lệch dữ liệu và read reconciliation có thể ảnh hưởng thời gian đọc.

- `LOCAL_ONE` thường có yêu cầu xác nhận đọc thấp hơn, nhưng có thể quan sát dữ liệu chưa hội tụ.
- `LOCAL_QUORUM` yêu cầu nhiều replica trong datacenter địa phương hơn, phụ thuộc RF và trạng thái cluster, thường đánh đổi độ trễ/khả dụng với mức bảo đảm đọc khác.
- Cả hai **không tạo chỉ mục cho regular column** và không tự giảm số partition ứng viên do `WHERE` biểu diễn.

Vì vậy khi truy vấn lọc chậm, cần tách hai nguyên nhân: **đường đọc quá rộng** và **chi phí phục vụ/đồng bộ replica**. Chọn consistency theo cam kết dữ liệu, không dùng như mẹo thay thế thiết kế khóa.

## 9. Đo thực tế bằng tracing và metrics

### 9.1. So sánh ba câu truy vấn trong cqlsh

Trên **môi trường lab** và cùng tập dữ liệu, bật tracing:

```sql
TRACING ON;

-- A: chỉ đọc theo khóa.
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20';

-- B: lọc regular column trong đúng partition.
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;

-- C: thu hẹp cả clustering range trước khi lọc.
SELECT occurred_at, event_id, event_type, device
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
  AND device = 'mobile'
ALLOW FILTERING;

TRACING OFF;
```

Quan sát số partition/dòng được đọc, thời gian thực thi, hoạt động coordinator/replica và thông tin read stages được trace trong phiên bản cluster. Một số trace chỉ cho thấy các bước thực thi chứ không cung cấp chính xác số bytes đĩa; cần kết hợp với metrics và bài thử tải.

**Không bật tracing toàn bộ truy vấn production liên tục**: tracing tạo thêm tải. Sử dụng có chọn lọc trên môi trường thử nghiệm hoặc request kiểm soát, theo quy trình vận hành.

### 9.2. Những chỉ số đáng thu thập

| Chỉ số | Tại sao cần |
| --- | --- |
| p50/p95/p99 latency theo câu truy vấn | Nhận diện tail latency khó dự đoán do dữ liệu phân bố lệch. |
| Số partition được truy cập và kích cỡ partition | Đánh giá fan-out và hot/wide partitions. |
| Tombstone scanned / warnings | Phát hiện nhiều dữ liệu đã xóa/hết TTL phải xử lý. |
| Read timeouts, unavailable và retries | Đo mức độ quá tải và rủi ro khuếch đại yêu cầu. |
| SSTable per read, cache hit và compaction backlog | Quan sát read amplification và áp lực storage. |
| Node/coordinator load và replica latency | Phân biệt kế hoạch đọc rộng với tình trạng hạ tầng. |
| QPS, độ dài `IN`, page size và concurrency | Biết áp lực thực tế từ ứng dụng. |

Benchmark nên dùng phân bố dữ liệu gần thực tế: tenant lớn/nhỏ, partition ngày có nhiều sự kiện, phần lớn dòng không khớp, dữ liệu có TTL/tombstone và request đồng thời. Một câu truy vấn nhanh trên lab 10 dòng **không chứng minh** tính ổn định trên production.

## 10. Thay ALLOW FILTERING bằng đường truy cập phù hợp

### 10.1. Thiết kế thêm bảng theo truy vấn

Nếu màn hình thường xuyên yêu cầu “tất cả sự kiện `VIEW` của tenant trong một ngày, theo thời gian”, có thể xây bảng đọc:

```sql
CREATE TABLE IF NOT EXISTS events_by_tenant_day_type (
    tenant_id uuid,
    event_day date,
    event_type text,
    occurred_at timestamp,
    event_id uuid,
    device text,
    detail text,
    PRIMARY KEY (
        (tenant_id, event_day, event_type),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at ASC, event_id ASC);
```

Ở bảng này, bộ ba `(tenant_id, event_day, event_type)` là **partition key đầy đủ**. Truy vấn:

```sql
SELECT occurred_at, event_id, device
FROM events_by_tenant_day_type
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW';
```

định vị partition theo loại sự kiện, **không cần `ALLOW FILTERING`**. Vì bảng này mới tạo, phải **nạp/duy trì dữ liệu riêng** thì mới có kết quả; nó không tự đồng bộ từ `events_by_tenant_day`.

Đánh đổi:

- Tăng số bảng và số ghi trên mỗi sự kiện.
- Cần xử lý idempotency, retry, cập nhật và xóa/TTL giữa các bản sao dữ liệu nghiệp vụ.
- Các truy vấn khác, ví dụ “tất cả `device = mobile`”, có thể vẫn cần đường đọc khác.
- Không tạo partition quá lớn nếu một loại sự kiện cực phổ biến; điều chỉnh bucket phù hợp.

Điểm mạnh của Cassandra là **denormalization có chủ đích theo truy vấn**, không phải ép một bảng tổng quát thực hiện mọi kiểu lọc.

### 10.2. Sử dụng chỉ mục khi phù hợp

Ở các phiên bản Cassandra hỗ trợ **Storage-Attached Index (SAI)** (ví dụ Apache Cassandra 5.0), chỉ mục có thể cung cấp đường truy cập cho một số điều kiện trên regular column:

```sql
-- Minh họa cú pháp trên môi trường hỗ trợ SAI.
-- Chỉ tạo sau khi đánh giá phiên bản, cardinality và chi phí ghi.
CREATE CUSTOM INDEX IF NOT EXISTS events_type_sai
ON events_by_tenant_day (event_type)
USING 'StorageAttachedIndex';
```

**Không coi SAI là phép màu**: hiệu năng vẫn phụ thuộc độ chọn lọc, phân bố giá trị, tổ hợp điều kiện, kích thước dữ liệu, cách index được quản lý và lượng công việc để trả các dòng. Điều kiện kết hợp hoặc cú pháp được hỗ trợ cũng phải kiểm tra đúng phiên bản. Một index trên `event_type` không tự bảo đảm “truy vấn mọi `VIEW` toàn cluster” luôn rẻ ở QPS lớn.

Khi nào cần cân nhắc?

| Tình huống | Giải pháp có thể phù hợp | Cần đo |
| --- | --- | --- |
| Một partition nhỏ, lọc ít lần theo regular column | `ALLOW FILTERING` có kiểm soát | Kích thước partition, p99, tombstone. |
| Một partition rất lớn, API nóng theo `event_type` | Bảng theo `(tenant, ngày, loại)` | Kích thước từng partition, chi phí ghi/đồng bộ. |
| Truy vấn có tính chọn lọc, điều kiện linh hoạt | SAI nếu phiên bản hỗ trợ | Index selectivity, latency, write/read overhead. |
| Đếm/tổng hợp toàn hệ thống theo loại sự kiện | Bảng summary/streaming analytics | Độ mới, sai lệch, backfill, idempotency. |
| Quét toàn bộ bảng phục vụ báo cáo offline | Công cụ phân tích/batch có kiểm soát | Thời gian chạy, concurrency, giới hạn tài nguyên. |

### 10.3. Đọc nhỏ rồi lọc ở ứng dụng có được không?

Được cân nhắc khi **tập dữ liệu đầu vào thật sự nhỏ và có giới hạn trên rõ ràng**. Ví dụ một partition chỉ có vài chục sự kiện trong một giờ, đọc một clustering range đủ ngắn rồi lọc ở Java có thể dễ đo lường hơn một `ALLOW FILTERING` trên tập lớn.

Nhưng lựa chọn này **truyền những dòng không cần thiết tới client**, tăng băng thông và RAM ứng dụng. Với partition lớn, nó thường kém hơn việc thiết kế đường truy vấn phù hợp. Không chuyển bài toán scan toàn bảng từ server sang Java rồi coi đó là tối ưu.

## 11. Java Driver: giới hạn ranh giới đọc và bind tham số

Ví dụ dùng **Apache Cassandra Java Driver 4.x** và Java 15+ (text blocks). Giả định `CqlSession session` đã kết nối với keyspace `cassandra_filter_lab`.

### 11.1. Một tình huống lọc có giới hạn

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

UUID tenantId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement prepared = session.prepare("""
    SELECT occurred_at, event_id, event_type, device
    FROM events_by_tenant_day
    WHERE tenant_id = ?
      AND event_day = ?
      AND occurred_at >= ?
      AND occurred_at < ?
      AND device = ?
    ALLOW FILTERING
    """);

BoundStatement statement = prepared.bind(
    tenantId,
    day,
    Instant.parse("2026-11-20T09:00:00Z"),
    Instant.parse("2026-11-20T12:00:00Z"),
    "mobile"
).setPageSize(50);

for (Row row : session.execute(statement)) {
    System.out.printf("%s %s %s%n",
        row.getInstant("occurred_at"),
        row.getUuid("event_id"),
        row.getString("event_type")
    );
}
```

Với dữ liệu lab: `VIEW` lúc 10:00 và `CLICK` lúc 11:00. Đây là ví dụ **minh họa cách dùng `ALLOW FILTERING` một cách có ranh giới**, không phải khuyến nghị mặc định cho mọi endpoint.

### 11.2. Chính sách bảo vệ API

Ứng dụng nên áp các ràng buộc trước khi truy vấn:

1. Xác thực/ủy quyền để `tenant_id` không thể bị dùng truy cập tenant khác.
2. Bắt buộc chọn `event_day` hoặc danh sách bucket ngắn với trần rõ ràng.
3. Kiểm tra hai cận thời gian, giới hạn độ dài khoảng (ví dụ chỉ vài giờ khi phù hợp nghiệp vụ).
4. Giới hạn số request đồng thời, timeout và retry; không tự động retry vô hạn trên truy vấn scan tốn kém.
5. Log query shape, candidate partitions, latency và các cảnh báo Cassandra mà **không làm lộ dữ liệu nhạy cảm**.
6. Chuyển sang bảng đọc/index phù hợp nếu loại lọc này trở thành API nóng hoặc tail latency vượt mục tiêu.

Ví dụ kiểm tra giới hạn thời gian ở Java:

```java
import java.time.Duration;
import java.time.Instant;

Instant start = Instant.parse("2026-11-20T09:00:00Z");
Instant end = Instant.parse("2026-11-20T12:00:00Z");
Duration window = Duration.between(start, end);

if (window.isNegative() || window.isZero()
        || window.compareTo(Duration.ofHours(6)) > 0) {
    throw new IllegalArgumentException("Khoang thoi gian khong hop le");
}
```

Giới hạn sáu giờ chỉ là **ví dụ một chính sách API**, không phải ngưỡng an toàn của Cassandra. Một tenant có thể ghi hàng triệu sự kiện trong sáu giờ; cần kiểm soát kích thước partition và đo hiệu năng thực.

### 11.3. Xử lý lỗi đúng loại

- **InvalidQuery / yêu cầu `ALLOW FILTERING`:** vấn đề CQL hoặc đường truy vấn; tăng timeout không chữa được.
- **Timeout / Unavailable:** xem xét replica, consistency, độ dài dải đọc, fan-out và tải; tránh retry gây bão yêu cầu.
- **Đọc ra dữ liệu không đồng nhất giữa các lần:** kiểm tra replication/consistency, TTL, ghi/xóa đồng thời và repair; paging state không tạo snapshot bất biến.
- **Response có ít dòng nhưng chậm:** xem xét số dòng bị lọc, tombstone, compaction backlog, SSTable reads và index selectivity (nếu có).

## 12. Những hiểu lầm thường gặp

| Nhận định | Vì sao sai hoặc thiếu | Cách tiếp cận |
| --- | --- | --- |
| “`ALLOW FILTERING` tăng tốc truy vấn.” | Nó chỉ chấp nhận một số kiểu thực thi có filtering; không tự tạo đường truy cập. | Giới hạn partition/range hoặc thiết kế bảng/index. |
| “Đã biết partition key nên lọc cột nào cũng rẻ.” | Một partition có thể rất lớn; regular column vẫn có thể buộc duyệt nhiều dòng. | Kiểm tra số dòng ứng viên, bucket và latency. |
| “Trả 2 dòng nghĩa là Cassandra chỉ đọc 2 dòng.” | Có thể đã kiểm tra 5, 50.000 hay nhiều mục vật lý hơn. | Đo tracing/metrics, không suy từ response size. |
| “`LIMIT 1` bảo đảm chỉ kiểm tra một dòng.” | Có thể phải qua nhiều dòng không khớp mới tìm được một dòng phù hợp. | Tạo đường truy cập đúng khóa/index. |
| “`PER PARTITION LIMIT 1` làm truy vấn chỉ chạm một partition.” | Giới hạn mỗi partition, không giảm số khóa partition trong `WHERE`. | Giới hạn danh sách bucket/`IN`. |
| “`event_type = 'VIEW'` luôn tìm được từ toàn bảng.” | Không có index phù hợp và không có partition key; có thể scan rộng hoặc bị từ chối. | Bảng theo truy vấn/index/analytics. |
| “Thêm `ALLOW FILTERING` sửa mọi lỗi `WHERE`.” | Một số tổ hợp điều kiện khóa vẫn không được hỗ trợ hoặc bị chính sách giới hạn. | Kiểm tra primary key và cú pháp phiên bản. |
| “Page size 20 nghĩa Cassandra chỉ đọc 20 dòng.” | Page size điều tiết fetch, không loại chi phí lọc trước khi có kết quả. | Thiết kế đúng phạm vi đọc. |
| “SAI giải quyết mọi truy vấn hiếm và phổ biến như nhau.” | Hiệu năng phụ thuộc cardinality, selectivity, QPS và phiên bản. | Benchmark và cân nhắc bảng chuyên biệt. |
| “Tăng timeout là cách khắc phục lọc chậm.” | Có thể làm yêu cầu chậm tích tụ và tăng quá tải. | Giảm scan, đo p99, quản lý concurrency và retry. |

## 13. Bài tập thực hành và đáp án

### Bài 1. Đếm ứng viên và kết quả trong một partition

**Đề:** Tenant A/ngày 20 có năm sự kiện. Truy vấn `event_type = 'VIEW' ALLOW FILTERING` trả bao nhiêu dòng? Bao nhiêu dòng logic thuộc partition ứng viên trước khi xét `event_type`?

**Đáp án:** **2 dòng kết quả**, **5 dòng ứng viên** trong lab; tỷ lệ khớp `2/5 = 40%`. Con số năm không phải khẳng định chính xác số record vật lý được đọc.

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND event_type = 'VIEW'
ALLOW FILTERING;
```

### Bài 2. Giảm phạm vi trước khi lọc

**Đề:** Chỉ tìm những sự kiện `device = 'mobile'` từ 09:00 đến trước 12:00 trong ngày 20 của tenant A.

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at >= '2026-11-20 09:00:00+0000'
  AND occurred_at <  '2026-11-20 12:00:00+0000'
  AND device = 'mobile'
ALLOW FILTERING;
```

Trong lab: **3 dòng ứng viên trong khoảng**, **2 dòng khớp** lúc 10:00 và 11:00.

### Bài 3. LIMIT có đủ để tránh scan rộng không?

**Đề:** Vì sao câu sau vẫn có thể chậm dù chỉ lấy một dòng?

```sql
SELECT tenant_id, event_day, event_id
FROM events_by_tenant_day
WHERE event_type = 'LOGOUT'
LIMIT 1
ALLOW FILTERING;
```

**Đáp án:** Không có full partition key và không có index trên `event_type`. Để tìm một dòng `LOGOUT`, Cassandra có thể phải kiểm tra nhiều partition/dòng trước khi gặp kết quả. `LIMIT 1` chỉ khống chế **dòng kết quả**, không khống chế chắc chắn **khối lượng đọc**.

### Bài 4. Thiết kế lại bảng

**Đề:** Một API liên tục đọc tất cả `VIEW` của một tenant/ngày theo thời gian. Nên sửa bằng `ALLOW FILTERING` hay thiết kế bảng?

**Đáp án gợi ý:** Với QPS cao hoặc partition lớn, nên cân nhắc bảng `events_by_tenant_day_type` có composite partition key `(tenant_id, event_day, event_type)` và clustering `(occurred_at, event_id)`. Truy vấn theo `VIEW` trở thành đọc một partition phù hợp; cần duy trì dữ liệu denormalized và xử lý ghi/xóa/TTL. Nếu điều kiện linh hoạt và Cassandra hỗ trợ, đánh giá SAI bằng benchmark.

### Bài 5. Fan-out nhiều ngày

**Đề:** Tenant A có 30 partition ngày được biết; trung bình 10.000 sự kiện/ngày, và khoảng 1% là `VIEW`. Không có index, request lọc `VIEW` trên toàn bộ 30 ngày sẽ có lượng ứng viên và kết quả ước lượng bao nhiêu?

**Đáp án:**

```text
Partition-key candidates = 30
Ứng viên logic ≈ 30 × 10000 = 300000
Kết quả kỳ vọng ≈ 300000 × 1% = 3000 dòng
```

Đây là **ước lượng theo giả định trung bình**, không phải con số storage engine đọc chính xác. Tỷ lệ `1%` không khiến Cassandra tự truy trực tiếp chỉ 3.000 dòng nếu chưa có đường truy cập theo `event_type`. Phải cân nhắc chia bucket, hạn chế khoảng, bảng chuyên biệt hoặc index.

### Bài 6. Phân biệt lỗi truy vấn và lỗi vận hành

**Tình huống:** Một truy vấn thiếu partition key báo lỗi yêu cầu `ALLOW FILTERING`; sau khi thêm từ khóa thì API có p99 tăng mạnh và timeout.

**Đáp án gợi ý:** Bước đầu sửa cú pháp chỉ làm kiểu quét/lọc được cho phép, **không làm nó có hiệu năng ổn định**. Cần đo fan-out, kích thước partition, tombstones, trace, trạng thái replica và consistency; sau đó giảm phạm vi bằng khóa/clustering hoặc xây bảng/index phù hợp. Retry và tăng timeout đơn thuần có thể làm tải nặng hơn.

## 14. Checklist trước khi dùng ALLOW FILTERING

1. **Khóa:** đã biết toàn bộ partition key chưa? Nếu dùng `IN`, có bao nhiêu full partition keys ứng viên?
2. **Clustering:** đã tận dụng khoảng theo clustering key để giảm số dòng ứng viên chưa?
3. **Độ chọn lọc:** ước lượng `N` dòng ứng viên và `M` dòng khớp; có dữ liệu lệch/hot partition hoặc nhiều trường hợp `M = 0` không?
4. **Kích thước:** số dòng và bytes mỗi partition, tombstone/TTL, SSTable read amplification có thể lớn đến mức nào?
5. **Giới hạn:** có đang nhầm `LIMIT`, `PER PARTITION LIMIT` hoặc driver page size với khả năng định vị dữ liệu không?
6. **Đo lường:** đã so sánh tracing, p95/p99 latency, read timeouts, tombstones và concurrency trên dữ liệu gần production chưa?
7. **Giải pháp:** có nên lập bảng theo truy vấn, dùng SAI phù hợp, tổng hợp trước hoặc giữ lọc trên một tập thật nhỏ?
8. **Vận hành:** consistency, replication, repair, compaction, retry và timeout có phù hợp với tải đọc và yêu cầu dữ liệu không?
9. **Ứng dụng Java:** đã bind đúng kiểu, áp authorization theo tenant, giới hạn số bucket/khoảng giờ và có kế hoạch chống quá tải chưa?

**Ghi nhớ:** `ALLOW FILTERING` không làm truy vấn trở nên có chỉ mục; nó cho phép Cassandra **đọc và kiểm tra dữ liệu nhiều hơn số dòng cần trả về**. Hãy đánh giá **partition fan-out, dòng ứng viên, tombstone/TTL và chi phí replica** thay vì chỉ nhìn `LIMIT` hay kích thước response. Với truy vấn nóng, ưu tiên **mô hình bảng theo đường đọc** hoặc chỉ mục/tổng hợp được đánh giá trên tải thực tế.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT và ALLOW FILTERING](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: Primary Key và Clustering Columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Documentation — Storage-Attached Indexing](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-overview.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
