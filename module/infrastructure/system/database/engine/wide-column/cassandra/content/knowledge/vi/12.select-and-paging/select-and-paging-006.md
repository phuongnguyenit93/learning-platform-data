# LIMIT, PER PARTITION LIMIT và phạm vi giới hạn trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `LIMIT` (giới hạn tổng số dòng kết quả) với `PER PARTITION LIMIT` (giới hạn số dòng lấy từ **mỗi partition**).
2. Giải thích **phạm vi giới hạn** theo ba góc nhìn: số partition cần truy cập, số dòng khớp điều kiện trong từng partition và số dòng cuối cùng trả về.
3. Kết hợp hai mệnh đề giới hạn với `WHERE`, clustering order và `ORDER BY` mà không nhầm lẫn về thứ tự hay kết quả.
4. Dự đoán kết quả từ một ví dụ CQL gồm nhiều partition có số dòng khác nhau, cả khi dữ liệu rỗng hoặc không có đủ dòng.
5. Phân biệt giới hạn kết quả của CQL với **page size** và **paging state** trong Cassandra Java driver.
6. Nhận biết vì sao `LIMIT 10` không tự sửa truy vấn cần scan rộng, không bảo đảm chỉ đọc 10 dòng trên đĩa và không thay cho thiết kế bảng theo truy vấn.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trong Apache Cassandra, một hệ cơ sở dữ liệu wide-column phân tán, **partition key** định vị nơi lưu dữ liệu, **clustering columns** tổ chức thứ tự các dòng trong partition, và **consistency level** tác động đến việc đọc từ replica nào. Các mệnh đề giới hạn chỉ có ý nghĩa chính xác khi đặt trong bối cảnh mô hình dữ liệu, phân vùng và yêu cầu truy vấn của ứng dụng Java.

## 1. Ba câu hỏi phải tách biệt khi đọc một truy vấn

Hãy xem câu lệnh khái quát:

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = ?
  AND day_bucket IN (?, ?, ?)
PER PARTITION LIMIT 2
LIMIT 3;
```

Để hiểu câu lệnh này, cần trả lời ba câu hỏi **khác nhau**:

| Câu hỏi | Bộ phận quyết định chính | Ý nghĩa |
| --- | --- | --- |
| **Những partition nào được chọn để đọc?** | Partition key trong `WHERE` | Tập các khóa phân vùng đầy đủ, có thể nằm trên nhiều node. |
| **Trong mỗi partition, những dòng nào có thể khớp?** | Clustering conditions, filters, clustering order | Một đoạn liên tiếp hoặc tập dòng theo mô hình khóa; số lượng có thể rất lớn. |
| **Trả về tối đa bao nhiêu dòng?** | `PER PARTITION LIMIT` và `LIMIT` | Giới hạn theo từng partition và giới hạn tổng kết quả. |

Một câu `SELECT` có thể định vị 100 partition nhưng chỉ trả 5 dòng. Ngược lại, truy vấn chỉ một partition có thể trả hàng nghìn dòng nếu partition rất lớn. Vì vậy **số dòng trả về không phải số partition được truy cập**, và cũng không phải số dòng/cell mà storage engine phải kiểm tra.

## 2. Cú pháp và quy tắc ý nghĩa

Khung cú pháp phù hợp cho các ví dụ:

```sql
SELECT column_name [, column_name ...]
FROM keyspace_name.table_name
[WHERE primary_key_conditions]
[ORDER BY clustering_column [ASC | DESC] [, ...]]
[PER PARTITION LIMIT n]
[LIMIT m];
```

Trong đó `n` và `m` là các **số nguyên dương** dùng để giới hạn số dòng; trong ứng dụng thực tế, hãy chọn giới hạn nhỏ và có trần được kiểm soát.

- `LIMIT m`: truy vấn trả về **không quá `m` dòng tổng cộng**. Trong truy vấn một partition, đó là giới hạn số dòng lấy từ partition ấy.
- `PER PARTITION LIMIT n`: truy vấn trả về **không quá `n` dòng từ mỗi partition** mà nó duyệt. Nếu có nhiều partition, tổng số dòng vẫn có thể lớn hơn `n`.
- Nếu có cả hai, **hai giới hạn cùng áp dụng**: không partition nào vượt `n` dòng và toàn bộ kết quả không vượt `m` dòng.
- Nếu thiếu `PER PARTITION LIMIT`, không có giới hạn riêng theo partition do mệnh đề này áp đặt.
- Nếu thiếu `LIMIT`, mệnh đề giới hạn tổng số dòng này không được áp đặt; việc driver/cqlsh chia trang khi fetch **không phải** một `LIMIT` ngầm về toàn bộ kết quả.
- Hai mệnh đề không tạo partition key, chỉ mục hay một thứ tự sắp xếp mới.

Thứ tự cú pháp là **`PER PARTITION LIMIT` trước `LIMIT`**. Một số tính năng CQL khác như `DISTINCT`, `GROUP BY` và tổng hợp có quy tắc riêng; các ví dụ trong bài sử dụng `SELECT` các dòng thông thường để diễn giải nhất quán số dòng.

## 3. Dữ liệu lab: một tenant, ba partition theo ngày

Giả sử ứng dụng có API xem lịch sử sự kiện của một tenant trong ngày, hoặc xem một số ngày cụ thể. Mỗi cặp `(tenant_id, day_bucket)` là **một partition**.

### 3.1. Tạo keyspace và bảng

```sql
-- Môi trường lab một node; không dùng SimpleStrategy/RF=1
-- làm mẫu triển khai production đa node, đa datacenter.
CREATE KEYSPACE IF NOT EXISTS cassandra_limit_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_limit_lab;

CREATE TABLE IF NOT EXISTS events_by_tenant_day (
    tenant_id uuid,
    day_bucket date,
    created_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    PRIMARY KEY ((tenant_id, day_bucket), created_at, event_id)
) WITH CLUSTERING ORDER BY (created_at DESC, event_id DESC);
```

Giải thích khóa:

- Cặp `(tenant_id, day_bucket)` là **composite partition key**. Các ngày khác nhau của cùng tenant là những partition khác nhau.
- `created_at` và `event_id` là **clustering columns**; mặc định các dòng trong mỗi partition được duyệt theo thời gian giảm dần, với `event_id` làm khóa phân biệt khi timestamp trùng.
- `event_type` và `detail` là cột thường, không thể tự động dùng làm chỉ mục hay `ORDER BY` tùy ý.

### 3.2. Thêm dữ liệu mẫu

```sql
-- Tenant A, ngày 20/11: bốn dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem danh sach don'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Mo chi tiet don'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Thanh toan'
);

-- Tenant A, ngày 21/11: hai dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21', '2026-11-21 09:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'LOGIN', 'Dang nhap ngay hai'
);

INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21', '2026-11-21 15:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'VIEW', 'Xem bao cao'
);

-- Tenant A, ngày 22/11: một dòng.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-22', '2026-11-22 16:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGOUT', 'Dang xuat'
);

-- Tenant B, ngày 20/11: partition khác.
INSERT INTO events_by_tenant_day
    (tenant_id, day_bucket, created_at, event_id, event_type, detail)
VALUES (
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'Tenant thu hai'
);
```

Với một bảng mới chỉ có các `INSERT` trên, dữ liệu phân bố như sau:

| Partition key | Số dòng | Thứ tự `created_at DESC` |
| --- | ---: | --- |
| Tenant A, ngày 20/11 | 4 | 11:00, 10:00, 09:00, 08:00 |
| Tenant A, ngày 21/11 | 2 | 15:00, 09:00 |
| Tenant A, ngày 22/11 | 1 | 16:00 |
| Tenant B, ngày 20/11 | 1 | 12:00 |

Truy vấn **tenant A với ba ngày 20, 21, 22** nhắm đến **ba partition chứa tổng cộng bảy dòng**. Partition của tenant B không thuộc tập này. Các `INSERT` dùng primary key cố định nên chạy lại trên cùng bảng là upsert, không tự sinh thêm dòng trùng khóa.

## 4. LIMIT: giới hạn toàn bộ kết quả

### 4.1. Một partition, lấy N dòng theo thứ tự clustering

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 2;
```

Kết quả dự kiến:

| `created_at` (UTC) | `event_type` |
| --- | --- |
| 20/11 11:00 | `PAY` |
| 20/11 10:00 | `CLICK` |

Đây là truy vấn có đường đọc rất rõ: `WHERE` định vị **một partition**, `ORDER BY` phù hợp với clustering order và `LIMIT 2` giữ tối đa hai dòng đầu tiên theo thứ tự đó. Với yêu cầu “hai sự kiện mới nhất trong một ngày”, đây là mẫu truy vấn thích hợp.

Nếu thay `LIMIT 2` bằng `LIMIT 10` thì partition này **chỉ có bốn dòng**, nên kết quả vẫn là bốn dòng. `LIMIT` là **giới hạn trên**, không yêu cầu Cassandra sinh đủ số dòng đã đặt.

### 4.2. LIMIT nhưng không có ORDER BY phù hợp

```sql
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
LIMIT 2;
```

Trong bảng này, truy vấn một partition vẫn duyệt theo **clustering order mặc định**, là `created_at DESC, event_id DESC`. Tuy vậy, viết `ORDER BY` tường minh khi API có yêu cầu thứ tự sẽ làm hợp đồng truy vấn dễ đọc hơn.

Không viết:

```sql
-- Không hợp lệ: event_type là cột thường, không phải clustering key.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY event_type ASC
LIMIT 2;
```

`LIMIT` không khiến `ORDER BY` trên cột thường trở nên hợp lệ.

### 4.3. Nhiều partition, LIMIT vẫn là giới hạn toàn kết quả

```sql
SELECT day_bucket, created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
LIMIT 3;
```

Truy vấn định vị **ba partition**, chứa tổng bảy dòng theo dữ liệu mẫu, nhưng chỉ trả tối đa **ba dòng tất cả**. Không được diễn giải thành “ba dòng cho ngày 20, ba dòng cho ngày 21 và ba dòng cho ngày 22”.

Quan trọng hơn, **không được suy từ `LIMIT 3` rằng kết quả là ba sự kiện mới nhất trong cả ba ngày**. Một partition có thứ tự clustering riêng; truy vấn `IN` chạm nhiều partition không phải mặc nhiên là một bảng đã sắp toàn cục theo `created_at`. Nếu cần top N toàn cục, thiết kế cách đọc và hợp nhất riêng.

## 5. PER PARTITION LIMIT: giới hạn riêng cho từng partition

### 5.1. Một danh sách partition, lấy tối đa hai dòng từ mỗi partition

```sql
SELECT day_bucket, created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 2;
```

Với dữ liệu mẫu:

| Partition | Số dòng thực tế | Giới hạn `2` | Số dòng có thể trả |
| --- | ---: | ---: | ---: |
| Tenant A, 20/11 | 4 | 2 | 2 |
| Tenant A, 21/11 | 2 | 2 | 2 |
| Tenant A, 22/11 | 1 | 2 | 1 |
| **Tổng** | **7** | **Giới hạn theo từng partition** | **5** |

Trong mỗi partition, các dòng được chọn theo clustering order `DESC`; do đó các sự kiện được giữ lại là:

- Ngày 20: `PAY 11:00` và `CLICK 10:00`.
- Ngày 21: `VIEW 15:00` và `LOGIN 09:00`.
- Ngày 22: `LOGOUT 16:00`.

**Năm dòng là tổng sau khi áp giới hạn từng partition; không có bảo đảm các dòng này được ghép theo một thứ tự thời gian toàn cục.**

### 5.2. PER PARTITION LIMIT không giới hạn số partition

Ví dụ:

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

Truy vấn trả tối đa **một dòng từ mỗi partition**. Với ba partition có dữ liệu, nó có thể trả **ba dòng**, vẫn phải xét cả ba khóa phân vùng. `PER PARTITION LIMIT 1` **không** có nghĩa “chỉ truy vấn một partition”.

Nếu danh sách `IN` có 100 ngày, `PER PARTITION LIMIT 1` có thể dẫn đến tối đa 100 dòng nhưng vẫn có tới **100 partition-key candidates**. Nó không làm fan-out từ 100 partition trở thành một.

### 5.3. Một partition: PER PARTITION LIMIT tương tự giới hạn dòng của partition đó

```sql
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
PER PARTITION LIMIT 2;
```

Ở truy vấn chỉ có một partition, kết quả tối đa hai dòng, giống số lượng tối đa của `LIMIT 2` trên cùng tập dòng và thứ tự đọc. Lợi ích riêng của `PER PARTITION LIMIT` thể hiện rõ nhất khi truy vấn chạm **nhiều partition** hoặc khi muốn một giới hạn nhất quán theo từng partition.

### 5.4. Không có dữ liệu thì giới hạn không tạo dữ liệu

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-22', '2026-11-23')
PER PARTITION LIMIT 2;
```

Với dữ liệu mẫu, ngày 22 có một dòng và ngày 23 không có dòng, nên chỉ có **một dòng kết quả**. Cassandra vẫn phải xét khóa partition ngày 23 được nêu trong truy vấn nhưng không “bù” dòng cho đủ hạn mức.

## 6. Kết hợp PER PARTITION LIMIT và LIMIT

Hai giới hạn cùng xuất hiện trong câu lệnh:

```sql
SELECT day_bucket, created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 2
LIMIT 3;
```

Ở đây:

1. Mỗi partition đóng góp **không quá hai dòng**.
2. Tổng của toàn bộ result set là **không quá ba dòng**.
3. **Không có cam kết chia đều** ba dòng cho ba ngày; cũng không có cam kết kết quả là ba dòng có `created_at` lớn nhất trên toàn bộ các ngày.

Với truy vấn `SELECT` các dòng thông thường và không có biến đổi tổng hợp, có thể mô tả **giới hạn trên** bằng ký hiệu:

\[
R_{\max}\ \leq\ \min\left(L,\ \sum_{i=1}^{P}\min(p,\, r_i)\right)
\]

Trong đó:

- `P`: số partition được truy vấn (ứng viên).
- `r_i`: số dòng của partition thứ `i` thực sự **khớp điều kiện `WHERE`**.
- `p`: `PER PARTITION LIMIT`, nếu được chỉ định.
- `L`: `LIMIT`, nếu được chỉ định.

Với tenant A qua ba ngày, `r = (4, 2, 1)`, `p = 2`, `L = 3`:

```text
Tổng có thể lấy trước giới hạn toàn cục
    = min(2,4) + min(2,2) + min(2,1)
    = 2 + 2 + 1
    = 5 dòng

Sau LIMIT 3:
    tối đa min(3,5) = 3 dòng.
```

Ký hiệu chỉ **giải thích giới hạn số dòng**, không mô phỏng toàn bộ cơ chế thực thi nội bộ, không xác định partition nào sẽ được trả trước, và không dùng nguyên vẹn cho truy vấn aggregate, GROUP BY hay logic đặc biệt khác.

| Truy vấn trên tenant A và ba ngày | Trần theo partition | Trần tổng | Số dòng tối đa từ dữ liệu mẫu |
| --- | --- | --- | ---: |
| Không có hai mệnh đề giới hạn | Không có | Không có | 7 |
| `LIMIT 3` | Không có | 3 | 3 |
| `PER PARTITION LIMIT 2` | 2 | Không có | 5 |
| `PER PARTITION LIMIT 2 LIMIT 3` | 2 | 3 | 3 |
| `PER PARTITION LIMIT 1 LIMIT 10` | 1 | 10 | 3 |

## 7. “Phạm vi giới hạn” không chỉ là LIMIT: WHERE quyết định vùng đọc

Một truy vấn nhanh thường đạt được nhờ **hạn chế phạm vi bằng khóa** trước, rồi mới giới hạn số dòng trả về.

### 7.1. Giới hạn partition bằng partition key

```sql
-- Một partition được xác định chính xác.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
LIMIT 2;
```

Toàn bộ khóa phân vùng là `(tenant_id, day_bucket)`. Vì vậy Cassandra có thể định tuyến tới những replica lưu **một partition**. `LIMIT 2` sau đó giới hạn số dòng trả về từ partition này.

### 7.2. Giới hạn một khoảng clustering trong partition

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at <  '2026-11-20 11:00:00+0000'
ORDER BY created_at DESC, event_id DESC
LIMIT 1;
```

Đây là **một partition** và một khoảng nửa mở `[09:00, 11:00)` trên clustering column `created_at`. Dữ liệu mẫu có hai dòng khớp (09:00 và 10:00), nhưng kết quả lấy **`CLICK 10:00`** do clustering order giảm dần và `LIMIT 1`.

Phân biệt ba tầng giới hạn:

```text
WHERE tenant_id = A AND day_bucket = 20
    -> một partition

AND created_at >= 09:00 AND created_at < 11:00
    -> lát cắt trong partition: 09:00, 10:00

ORDER BY created_at DESC LIMIT 1
    -> một dòng kết quả: 10:00
```

Việc dùng khoảng clustering hợp lý thường giúp công việc đọc giới hạn hơn so với duyệt cả partition chỉ để trả `LIMIT 1`, nhất là khi yêu cầu nằm ở một khoảng thời gian cụ thể.

### 7.3. LIMIT không sửa được truy vấn không đủ partition key

```sql
-- Thiếu day_bucket: không đủ composite partition key.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
LIMIT 1;

-- event_type là cột thường; không có đường truy cập theo schema này.
SELECT created_at, event_type
FROM events_by_tenant_day
WHERE event_type = 'PAY'
LIMIT 1;
```

Những câu này **không trở thành truy vấn khóa hợp lệ chỉ nhờ `LIMIT 1`**. Để hỗ trợ tìm kiếm theo `event_type` trên nhiều tenant/ngày, ứng dụng cần mô hình bảng truy vấn khác hoặc một chỉ mục phù hợp với phiên bản Cassandra và tải thực tế.

Kể cả dùng `ALLOW FILTERING` để cho phép một số truy vấn lọc, `LIMIT 1` vẫn có thể phải sàng lọc rất nhiều dòng hoặc partition **trước khi tìm được dòng phù hợp**. Số dòng đầu ra nhỏ không đồng nghĩa chi phí tìm kiếm nhỏ.

### 7.4. LIMIT không thay đổi số partition trong IN

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
LIMIT 1;
```

Điều kiện khóa vẫn mô tả **ba partition ứng viên**. Tùy kế hoạch thực thi và thời điểm đạt giới hạn, hệ thống có thể không cần lấy hết mọi dòng từ mọi partition; tuy nhiên `LIMIT 1` **không cung cấp bảo đảm** rằng toàn bộ truy vấn chỉ định vị hoặc liên hệ đúng một partition. Đánh giá fan-out trước hết vẫn phải dựa trên tập khóa đầy đủ trong `WHERE`.

## 8. Số dòng trả về không phải chi phí đọc

Trong Cassandra phân tán, một câu `SELECT` có các loại chi phí khác nhau:

| Đại lượng | `LIMIT`/`PER PARTITION LIMIT` có làm thay đổi không? | Điều ảnh hưởng chính |
| --- | --- | --- |
| Số khóa partition trong `WHERE` | **Không đổi tập khóa được biểu diễn.** | Partition key, `=`, `IN`, token range. |
| Số dòng kết quả | **Có**, theo giới hạn toàn cục và từng partition. | Hai mệnh đề giới hạn, dữ liệu tồn tại, clustering range. |
| Dữ liệu truyền về client | Thường **giảm** khi giảm số dòng. | Số cột chọn, kích thước giá trị, page size. |
| Số row/cell được kiểm tra | **Không có trần trực tiếp bằng LIMIT.** | Tombstones, TTL, filtering, SSTable/memtable, cache. |
| Số node/replica được liên hệ | **Không suy ra chỉ từ LIMIT.** | Token placement, replication, consistency, trạng thái cluster. |
| Độ trễ p95/p99 | Có thể giảm, nhưng **không được bảo đảm**. | I/O, fan-out, concurrency, compaction/repair, tombstones, timeout/retry. |

Ví dụ: partition có nhiều bản ghi hết TTL hoặc nhiều tombstone có thể yêu cầu Cassandra duyệt qua các dấu xóa để tìm **một dòng còn sống**. Khi đó `LIMIT 1` không có nghĩa storage engine chỉ phải xử lý một cell.

Tương tự, `PER PARTITION LIMIT 1` trên 1.000 partition có thể giảm số dòng trả về, nhưng không giới hạn được **số partition** ứng viên. Trong API trực tuyến, điều quan trọng là giới hạn đồng thời **phạm vi khóa**, **kích thước partition**, **danh sách `IN`**, và **số dòng/bytes trả về**.

## 9. Giới hạn và phân trang là hai khái niệm khác nhau

### 9.1. So sánh LIMIT với page size

Giả sử câu truy vấn:

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 100;
```

Nếu Java driver đặt page size `20`:

- `LIMIT 100`: giới hạn **tổng số dòng** mà truy vấn được phép trả về.
- Page size `20`: hướng dẫn driver/server lấy kết quả theo **những đợt có kích thước mục tiêu**, chứ không bảo đảm chỉ có 20 dòng trong toàn truy vấn.
- Trong dữ liệu lab chỉ có **bốn dòng** của ngày 20, nên tổng kết quả chỉ có bốn dòng, dù `LIMIT` và page size đều lớn hơn.

Kích thước trang có thể chịu thêm các giới hạn thực thi hoặc dung lượng response; đừng dùng page size như cam kết tuyệt đối về kích thước payload. Với Java driver, duyệt hết `ResultSet` có thể kích hoạt fetch các trang còn lại.

### 9.2. Paging state để tiếp tục cùng truy vấn

Cassandra Java driver hỗ trợ paging state để tiếp tục duyệt kết quả của **cùng một câu truy vấn**. Khi gửi paging state trong request tiếp:

- Giữ nguyên CQL, bind values, điều kiện sắp xếp và các mệnh đề giới hạn thích hợp.
- Không trộn paging state của tenant/ngày này với truy vấn tenant/ngày khác.
- Không tự dựng hoặc sửa nội dung paging state; nếu cấp cho client, cần bảo vệ tính toàn vẹn và ràng buộc với quyền truy cập tương ứng.
- Paging không tạo snapshot bất biến giữa các lần đọc. Ghi/xóa/TTL và độ trễ replica có thể làm dữ liệu quan sát thay đổi.

`PER PARTITION LIMIT` vẫn áp dụng **theo partition của toàn bộ truy vấn**, không phải “n lần trên mỗi trang”. Vì vậy không được tự diễn giải các page liên tiếp thành những truy vấn mới mà đếm lại hạn mức từng partition.

### 9.3. CQL không có OFFSET kiểu SQL

Truy vấn dạng:

```sql
-- Không phải cú pháp phân trang được CQL hỗ trợ:
SELECT created_at, event_id
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
LIMIT 20 OFFSET 40;
```

không phải cách phân trang trong Cassandra. Dùng **driver paging state**, hoặc thiết kế **keyset cursor** theo clustering key (ví dụ bộ `(created_at, event_id)`) khi muốn phân trang theo khóa nghiệp vụ trong một partition.

### 9.4. LIMIT không giải quyết vấn đề sắp xếp đa partition

`PER PARTITION LIMIT 1` rất phù hợp để lấy **một dòng mới nhất ở mỗi partition** có clustering order giảm dần. Nhưng kết quả từ nhiều partition **không mặc nhiên** là “N dòng mới nhất toàn tenant”. Nếu API cần top N trên nhiều bucket ngày, có thể:

1. Chọn một số bucket ngày hữu hạn theo thời gian cần xem.
2. Đọc các dòng mới nhất của từng bucket với giới hạn phù hợp.
3. Hợp nhất bằng bộ khóa thứ tự `(created_at, event_id)` tại tầng ứng dụng, kiểm soát số dòng và concurrency.
4. Nếu đây là truy vấn nóng, xem xét bảng đọc riêng với partition/clustering phù hợp hơn.

Với dữ liệu cập nhật liên tục, chiến lược cursor cũng cần quy tắc nhất quán khi có sự kiện mới xuất hiện giữa các request.

## 10. Tích hợp với Java driver: bind LIMIT và kiểm soát kết quả

Ví dụ sử dụng Apache Cassandra Java Driver 4.x và Java 15+ (vì dùng text blocks). Giả định đã có `CqlSession session` kết nối đến keyspace `cassandra_limit_lab`.

### 10.1. Giới hạn kết quả trong một partition

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

UUID tenantId = UUID.fromString(
    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
);
LocalDate day = LocalDate.parse("2026-11-20");

PreparedStatement prepared = session.prepare("""
    SELECT created_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE tenant_id = ?
      AND day_bucket = ?
    ORDER BY created_at DESC, event_id DESC
    LIMIT ?
    """);

int requestedLimit = 2;
int safeLimit = Math.max(1, Math.min(requestedLimit, 100));

BoundStatement bound = prepared.bind(
    tenantId, day, safeLimit
).setPageSize(20);

for (Row row : session.execute(bound)) {
    System.out.printf("%s %s %s%n",
        row.getInstant("created_at"),
        row.getUuid("event_id"),
        row.getString("event_type")
    );
}
```

Ở đây:

- `LIMIT ?` dùng bind marker kiểu số nguyên; không nối chuỗi các giá trị do người dùng nhập vào CQL.
- `safeLimit` minh họa một **giới hạn ứng dụng** từ 1 đến 100; đây không phải giới hạn mặc định của Cassandra.
- `setPageSize(20)` thiết lập kích thước fetch của driver; nó không tăng giới hạn tổng kết quả lên 20 nếu CQL đã có `LIMIT 2`.
- Phương thức `row.getInstant(...)`, `getUuid(...)` phù hợp với kiểu `timestamp` và `uuid` đã khai báo.

### 10.2. Giới hạn theo từng partition với ba ngày cố định

```java
import java.time.LocalDate;

PreparedStatement perDay = session.prepare("""
    SELECT day_bucket, created_at, event_id, event_type
    FROM events_by_tenant_day
    WHERE tenant_id = ?
      AND day_bucket IN (?, ?, ?)
    PER PARTITION LIMIT 2
    LIMIT 5
    """);

BoundStatement query = perDay.bind(
    tenantId,
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-21"),
    LocalDate.parse("2026-11-22")
).setPageSize(3);

for (Row row : session.execute(query)) {
    System.out.printf("%s | %s | %s%n",
        row.getLocalDate("day_bucket"),
        row.getInstant("created_at"),
        row.getString("event_type")
    );
}
```

Với bảng lab, câu truy vấn có thể trả **năm dòng**: hai từ ngày 20, hai từ ngày 21 và một từ ngày 22; driver fetch theo các page có kích thước mục tiêu ba dòng. Các page **không tương ứng một-một với partition**, và thứ tự các dòng khi ghép nhiều partition không nên được xem là timeline được sắp toàn cục.

Trong ứng dụng thực tế, nếu danh sách ngày thay đổi, hãy kiểm soát số bucket được phép đọc, sử dụng câu truy vấn tham số hóa phù hợp với cardinality của danh sách và hạn chế fan-out. Đọc một tập nhỏ qua nhiều partition thường không đủ nhanh nếu số request đồng thời và số replica phải phối hợp tăng quá lớn.

### 10.3. Replication, consistency và xử lý lỗi

Trong cluster nhiều node, consistency level được cấu hình qua driver/session/statement. Nó quyết định yêu cầu xác nhận từ replica và ảnh hưởng mức độ mới của dữ liệu, độ trễ và khả năng sẵn sàng. **`LIMIT` không đổi mức consistency**, và `PER PARTITION LIMIT` không giảm replication factor.

Khi gặp lỗi:

- `InvalidQuery` do thiếu khóa, `ORDER BY` không hợp lệ hoặc cú pháp `LIMIT` sai là **lỗi thiết kế/truy vấn**; tăng timeout hay retry không sửa được.
- Timeout/unavailable cần xem xét sức khỏe replica, cấu hình consistency, số partition đang truy cập, kích thước dữ liệu, retry policy và tải của coordinator.
- Truy vấn bị chậm dù `LIMIT 1` có thể liên quan tombstones, compaction, repair, cache hoặc lọc nhiều dòng trước khi tìm thấy kết quả; dùng tracing/metrics để xác định nguyên nhân.

## 11. Lỗi thường gặp và cách sửa

| Quan niệm hoặc cách viết | Vấn đề thực tế | Cách xử lý |
| --- | --- | --- |
| `LIMIT 2` nghĩa là 2 dòng **mỗi ngày** | Giới hạn tổng số dòng của result set. | Dùng `PER PARTITION LIMIT 2` cho nhu cầu theo ngày. |
| `PER PARTITION LIMIT 2` trên ba partition nghĩa là tối đa 2 dòng tổng cộng | Mỗi partition có trần 2, tổng có thể đến 6. | Thêm `LIMIT` nếu cần trần tổng. |
| `PER PARTITION LIMIT 1` nghĩa chỉ đọc 1 partition | Vẫn có thể định vị toàn bộ khóa trong danh sách `IN`. | Giới hạn số bucket/partition ở `WHERE` hoặc API. |
| `LIMIT 10` bảo đảm chỉ đọc đúng 10 row/cell trên đĩa | Có thể phải quét tombstones, lọc, kiểm tra nhiều partition. | Giảm phạm vi đọc bằng khóa, quan sát tracing và partition size. |
| `LIMIT 10` làm truy vấn thiếu `day_bucket` trở nên hợp lệ | Không cung cấp composite partition key đầy đủ. | Chọn bucket cụ thể hoặc thiết kế bảng đọc khác. |
| `PER PARTITION LIMIT 1` lấy sự kiện mới nhất **trên toàn tenant** | Lấy tối đa một dòng của **mỗi partition**, không chọn top một toàn cục. | Hợp nhất có kiểm soát hoặc dùng bảng đọc phù hợp. |
| `ORDER BY event_type` hợp lệ nếu `LIMIT` nhỏ | `event_type` không là clustering column. | Thiết kế thứ tự trong primary key hoặc sắp tại ứng dụng trên tập nhỏ. |
| Page size 20 nghĩa câu `SELECT` trả nhiều nhất 20 dòng | Driver có thể fetch các trang tiếp theo. | Phân biệt `LIMIT` với page size/paging state. |
| `PER PARTITION LIMIT 2` áp lại 2 dòng cho mỗi trang fetch | Đây là giới hạn theo partition **trong truy vấn**, không theo page. | Tiếp tục truy vấn bằng đúng paging state. |
| `LIMIT 20 OFFSET 40` phân trang như SQL | CQL không hỗ trợ kiểu offset này. | Driver paging state hoặc keyset cursor phù hợp. |

## 12. Bài tập tự luyện có đáp án

### Bài 1. Hai dòng mới nhất trong một ngày

**Yêu cầu:** Lấy đúng tối đa hai sự kiện mới nhất của tenant A ngày 20/11/2026.

**Đáp án:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
ORDER BY created_at DESC, event_id DESC
LIMIT 2;
```

Kết quả: `PAY 11:00`, `CLICK 10:00`.

### Bài 2. Mỗi ngày một sự kiện

**Yêu cầu:** Trong ba ngày 20–22/11 của tenant A, lấy tối đa một dòng mới nhất từ mỗi ngày.

**Đáp án:**

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

Với dữ liệu mẫu, có ba dòng: `PAY 11:00` ngày 20, `VIEW 15:00` ngày 21 và `LOGOUT 16:00` ngày 22. Không khẳng định thứ tự toàn cục của ba dòng.

### Bài 3. Kết hợp hai giới hạn

**Yêu cầu:** Với ba ngày trên, mỗi ngày tối đa hai sự kiện, toàn bộ response tối đa ba sự kiện.

**Đáp án:**

```sql
SELECT day_bucket, created_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 2
LIMIT 3;
```

Truy vấn trả không quá ba dòng; mỗi partition không thể đóng góp nhiều hơn hai. Không có cam kết ba dòng thuộc ba ngày khác nhau.

### Bài 4. Đọc trong cửa sổ giờ

**Yêu cầu:** Trong ngày 20/11, chọn tối đa một sự kiện từ `09:00` đến trước `11:00` UTC, mới nhất trước.

**Đáp án:**

```sql
SELECT created_at, event_id, event_type
FROM events_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at >= '2026-11-20 09:00:00+0000'
  AND created_at <  '2026-11-20 11:00:00+0000'
ORDER BY created_at DESC, event_id DESC
LIMIT 1;
```

Kết quả: `CLICK 10:00`. `PAY 11:00` không thuộc khoảng vì cận trên dùng `<`.

### Bài 5. Phân tích fan-out và giới hạn

**Tình huống:** Một API nhận 100 ngày của một tenant, mỗi ngày là một partition, và thực hiện `PER PARTITION LIMIT 1 LIMIT 10`. Hỏi chắc chắn đã giảm số partition-key candidates xuống 10 chưa?

**Đáp án:** **Chưa.** `WHERE` vẫn mô tả 100 partition ứng viên. `PER PARTITION LIMIT 1` giới hạn mỗi partition đóng góp tối đa một dòng; `LIMIT 10` giới hạn kết quả tổng không quá mười dòng. Hai mệnh đề không thay đổi danh sách khóa được truy vấn. Cần kiểm soát số ngày/bucket ngay tại API và đánh giá chi phí fan-out trước khi thực thi.

## 13. Checklist thiết kế giới hạn cho API Cassandra

1. **Partition:** `WHERE` đã cung cấp đủ partition key chưa? Nếu có `IN`, có bao nhiêu khóa phân vùng đầy đủ cần định vị?
2. **Clustering:** Nếu chỉ lấy một khoảng, đã giới hạn trên clustering columns theo đúng thứ tự khóa và dùng cận bao gồm/loại trừ rõ ràng chưa?
3. **Ý nghĩa LIMIT:** Mục tiêu là **tối đa N dòng tổng cộng**, hay **tối đa N dòng mỗi partition**? Có cần cả hai trần không?
4. **Thứ tự:** `ORDER BY` có phù hợp với clustering order không? Có đang nhầm các dòng mới nhất của từng partition với top N toàn cục không?
5. **Paging:** Có phân biệt `LIMIT`, `PER PARTITION LIMIT`, driver page size và paging state không? Các request phân trang có giữ đúng tập điều kiện ban đầu không?
6. **Hiệu năng:** Có giới hạn bucket và concurrency, tránh partition quá lớn, theo dõi tombstones, compaction/repair, truy vấn chậm, p95/p99 và timeout không?
7. **Java/consistency:** Đã bind tham số đúng kiểu, đặt giới hạn số nguyên ở API, chọn consistency phù hợp replication và phân biệt lỗi query với timeout/unavailable chưa?

**Ghi nhớ:** `LIMIT` giới hạn **tổng số dòng trả về**; `PER PARTITION LIMIT` giới hạn **dòng của từng partition**. Muốn giới hạn **phạm vi phải đọc**, trước hết phải viết `WHERE` tương thích với partition key và clustering columns. Ba khái niệm ấy bổ sung cho nhau khi thiết kế truy vấn Cassandra phân tán, nhưng không thay thế nhau.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — CQL Data Manipulation: SELECT, PER PARTITION LIMIT, LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — CQL Data Definition: PRIMARY KEY, CLUSTERING ORDER](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
