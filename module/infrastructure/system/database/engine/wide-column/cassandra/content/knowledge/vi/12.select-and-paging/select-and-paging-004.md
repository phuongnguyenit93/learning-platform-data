# IN, khóa ghép và số phân vùng bị truy cập trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `IN` là tập các giá trị **rời rạc**, không phải phép tìm kiếm theo khoảng; phân biệt số partition, số dòng và số replica được đọc.
2. Phân tích cách Cassandra định vị partition khi có **composite partition key**, đặc biệt khi `IN` xuất hiện trên thành phần cuối của khóa phân vùng.
3. Đếm hoặc ước lượng số **khóa phân vùng đầy đủ** mà một truy vấn hoặc một nhóm truy vấn tạo ra.
4. Phân biệt `IN` trên **partition key** với `IN` trên **clustering column cuối**: hai truy vấn có thể có cùng số giá trị trong danh sách nhưng chi phí phân tán rất khác nhau.
5. Sử dụng `LIMIT` và `PER PARTITION LIMIT` đúng mục đích; nhận diện vấn đề thứ tự và phân trang khi đọc nhiều partition.
6. Chọn cách chia bucket, giới hạn danh sách `IN` và triển khai truy vấn trong Java driver phù hợp với tải thực tế.

Bài nằm trong chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trong mô hình wide-column của Apache Cassandra, hiệu quả đọc phụ thuộc trực tiếp vào **khóa phân vùng**, thiết kế bảng theo truy vấn và cấu trúc cluster phân tán. `IN` rất tiện cho một danh sách partition đã biết, nhưng mỗi giá trị bổ sung có thể làm phát sinh công việc đọc và liên lạc với replica. Mức consistency đọc ghi, replication, compaction, repair và xử lý lỗi của ứng dụng Java đều có thể ảnh hưởng độ trễ thực tế.

## 1. Nhắc lại: primary key, composite partition key và clustering columns

Xét khóa chính:

```sql
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
```

Các thành phần có ý nghĩa khác nhau:

| Thành phần | Vai trò | Hệ quả |
| --- | --- | --- |
| `tenant_id` + `day_bucket` | **Composite partition key** (hai giá trị kết hợp) | Cả cặp được dùng để tính token và tìm replica giữ partition. |
| `created_at` | Clustering column thứ nhất | Sắp các đơn hàng trong partition theo thời gian. |
| `order_id` | Clustering column thứ hai | Phân biệt các đơn có cùng `created_at`. |
| Cả bốn cột | **Full primary key** | Xác định tối đa một dòng của bảng. |

Đừng nhầm hai lược đồ này:

```sql
-- A. MỖI (tenant_id, day_bucket) LÀ MỘT PARTITION.
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)

-- B. MỖI tenant_id LÀ MỘT PARTITION.
-- day_bucket là clustering column đầu tiên.
PRIMARY KEY (tenant_id, day_bucket, created_at, order_id)
```

Trong lược đồ **A**, các ngày khác nhau của cùng tenant là những partition khác nhau. Trong lược đồ **B**, các ngày cùng tenant thuộc **một partition** và được sắp theo `day_bucket`. Vì thế, truy vấn nhiều ngày có chi phí và quy tắc `WHERE` khác nhau dù tên cột giống hệt.

Với lược đồ **A**, hãy hình dung:

```text
tenant_id = A
   |
   +-- (A, 2026-11-20) --> token P20 --> các replica sở hữu partition P20
   |
   +-- (A, 2026-11-21) --> token P21 --> các replica sở hữu partition P21
   |
   +-- (A, 2026-11-22) --> token P22 --> các replica sở hữu partition P22

Mỗi partition chứa các hàng theo (created_at, order_id).
P20, P21, P22 không nhất thiết ở cùng node hoặc nằm liền kề trong token ring.
```

Token được tính từ **toàn bộ** partition key; cố định `tenant_id` không tạo ra một vùng lưu trữ liên tục theo `day_bucket`. Đây là điểm xuất phát để hiểu `IN`.

## 2. Tạo dữ liệu mẫu có thể chạy trong cqlsh

Ví dụ ứng dụng đa tenant lưu đơn hàng theo bucket ngày để giới hạn kích thước mỗi partition. Mỗi ngày thường có nhiều đơn của một tenant.

```sql
-- Chỉ dùng replication_factor = 1 trong lab một node.
CREATE KEYSPACE IF NOT EXISTS cassandra_in_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_in_lab;

CREATE TABLE IF NOT EXISTS orders_by_tenant_day (
    tenant_id uuid,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    status text,
    amount_cents bigint,
    PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000011, 'CREATED', 129900
);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000012, 'PAID', 259900
);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21', '2026-11-21 10:15:00+0000',
    00000000-0000-4000-8000-000000000013, 'PAID', 49900
);

INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-22', '2026-11-22 13:00:00+0000',
    00000000-0000-4000-8000-000000000014, 'SHIPPED', 80000
);

-- Tenant thứ hai: không chia sẻ partition với tenant thứ nhất.
INSERT INTO orders_by_tenant_day
    (tenant_id, day_bucket, created_at, order_id, status, amount_cents)
VALUES (
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000015, 'CREATED', 99000
);
```

**Sơ đồ dữ liệu sau khi nạp:**

| Partition key | Số dòng trong dữ liệu mẫu | Các `order_id` (phần cuối) |
| --- | ---: | --- |
| Tenant A, ngày 20/11 | 2 | `...0011`, `...0012` |
| Tenant A, ngày 21/11 | 1 | `...0013` |
| Tenant A, ngày 22/11 | 1 | `...0014` |
| Tenant B, ngày 20/11 | 1 | `...0015` |

Có **bốn partition có dữ liệu**, chứa tổng cộng **năm dòng**. Chúng ta sẽ dùng các con số này để phân biệt *partition được truy cập*, *partition có dữ liệu* và *dòng trả về*. Lệnh `INSERT` trên cùng full primary key là upsert; chạy lại ví dụ không tạo thêm dòng trùng khóa.

## 3. IN trong WHERE có nghĩa gì?

`x IN (v1, v2, v3)` mô tả tập các giá trị ứng viên, tương tự ý nghĩa logic `x = v1 OR x = v2 OR x = v3`. Tuy nhiên, CQL **không hỗ trợ tùy ý mọi biểu thức `OR`**, và vị trí được phép dùng `IN` còn bị ràng buộc bởi primary key và phiên bản Cassandra.

Ví dụ trên **thành phần cuối của composite partition key**:

```sql
SELECT day_bucket, created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21');
```

Đây là truy vấn có **hai khóa phân vùng đầy đủ** cần xét:

```text
P1 = (tenant A, 2026-11-20)
P2 = (tenant A, 2026-11-21)

           +--> P1: 2 dòng
Coordinator|
           +--> P2: 1 dòng

Tổng: 2 partition, 3 dòng trả về với dữ liệu mẫu.
```

Điểm cần ghi nhớ:

- `IN` liệt kê các **giá trị cụ thể**, không đại diện cho dải liên tục từ ngày nhỏ nhất đến lớn nhất.
- Với tenant A và danh sách trên, có **hai partition riêng biệt** được định vị dù chúng nằm cùng một tenant.
- Nếu một ngày không có dữ liệu, khóa partition đó vẫn là **ứng viên cần tra cứu**, nhưng kết quả có thể không chứa dòng nào từ ngày ấy.
- Số phần tử trong `IN` **không phải** số dòng; mỗi partition có thể chứa 0, 1 hoặc rất nhiều dòng.
- Kết quả đọc nhiều partition **không có bảo đảm sắp xếp toàn cục theo ngày/thời điểm** chỉ vì mỗi partition có clustering order riêng.

Trong trường hợp chỉ cần một ngày, truy vấn bằng `=` thể hiện ý định rõ hơn:

```sql
SELECT created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20';
```

Câu này xét **một partition**, không phải hai. Dữ liệu mẫu của partition ấy có hai dòng.

## 4. Quy tắc IN trên khóa ghép

### 4.1. IN trên thành phần cuối của partition key

Theo tài liệu CQL, vị trí thông dụng được hỗ trợ là **cột cuối của partition key**, với các thành phần trước đó được ràng buộc bằng.

Đối với:

```sql
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
```

câu sau phù hợp:

```sql
SELECT day_bucket, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22');
```

Vì `tenant_id` đã cố định, mỗi giá trị `day_bucket` hoàn thiện một partition key.

Không đảo vai trò hai thành phần:

```sql
-- Sai với quy tắc IN của composite partition key này:
-- IN không nằm ở cột cuối của partition key.
SELECT order_id
FROM orders_by_tenant_day
WHERE tenant_id IN (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
)
AND day_bucket = '2026-11-20';
```

Để lấy nhiều tenant vào cùng một ngày với schema này, ứng dụng có thể gửi **mỗi tenant một truy vấn có đầy đủ partition key** hoặc dùng bảng đọc khác khi đây là mẫu truy vấn chính. Một API có thể cần tra cứu nhiều khóa độc lập; không phải tập khóa nào cũng biểu diễn được bằng **một câu CQL `IN` hợp lệ**.

### 4.2. Nếu partition key chỉ có một cột

Giả sử bảng riêng có định nghĩa:

```sql
CREATE TABLE IF NOT EXISTS tenant_settings (
    tenant_id uuid PRIMARY KEY,
    display_name text,
    default_locale text
);
```

Ở bảng này, chính `tenant_id` vừa là thành phần đầu vừa là **thành phần cuối duy nhất** của partition key. Vì vậy:

```sql
SELECT tenant_id, display_name, default_locale
FROM tenant_settings
WHERE tenant_id IN (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
);
```

là mẫu chọn **hai partition settings** hợp lệ, nếu cả hai tồn tại sẽ có tối đa hai dòng vì bảng không có clustering columns. Việc `IN` có thể dùng trên `tenant_id` ở bảng này **không suy ra** được rằng nó có thể dùng cùng cách trên thành phần đầu `tenant_id` của composite partition key ở bảng đơn hàng.

### 4.3. Khóa ghép ba thành phần: phải cố định tiền tố

Hình dung một bảng khác có:

```sql
PRIMARY KEY ((tenant_id, region_id, day_bucket), created_at, order_id)
```

Khi đó truy vấn theo một tenant, một vùng và nhiều ngày có hình dạng:

```sql
-- Minh họa quy tắc khóa cho bảng giả định.
SELECT created_at, order_id
FROM orders_by_tenant_region_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND region_id = 'north'
  AND day_bucket IN ('2026-11-20', '2026-11-21');
```

Đây là **hai composite partition keys**:

1. `(tenant A, north, 2026-11-20)`
2. `(tenant A, north, 2026-11-21)`

Các điều kiện `tenant_id = ...` và `region_id = ...` cố định tiền tố; `IN` nằm trên thành phần cuối `day_bucket`. Không giả định Cassandra có thể suy ra tất cả vùng hay tất cả ngày khi bỏ một thành phần của partition key. Tên bảng `orders_by_tenant_region_day` chỉ mang tính minh họa cấu trúc; không có lệnh tạo bảng ấy trong lab.

## 5. IN trên clustering column: số giá trị không đồng nghĩa số partition

`IN` cũng được hỗ trợ trên **cột cuối của toàn bộ primary key** khi những cột trước đã có điều kiện phù hợp.

Trong bảng lab:

```sql
PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)
```

`order_id` là cột cuối của primary key. Hãy truy vấn hai đơn có cùng `created_at`:

```sql
SELECT day_bucket, created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id IN (
      00000000-0000-4000-8000-000000000011,
      00000000-0000-4000-8000-000000000012
  );
```

Câu này cũng có **hai phần tử trong `IN`**, nhưng chỉ đọc **một partition** vì cặp `(tenant_id, day_bucket)` không đổi. `IN` ở đây chọn hai giá trị clustering key **bên trong partition**, có thể tương ứng hai dòng. So sánh:

| Câu truy vấn | Số phần tử `IN` | Số partition được định vị | Số dòng ở dữ liệu mẫu |
| --- | ---: | ---: | ---: |
| `day_bucket IN (20, 21)`, tenant A cố định | 2 | 2 | 3 |
| `order_id IN (11, 12)`, tenant A/ngày 20/`created_at` cố định | 2 | 1 | 2 |
| `day_bucket = 20`, tenant A cố định, không có `IN` | — | 1 | 2 |

**Kết luận về vị trí:** muốn biết số partition, trước hết hãy nhìn **partition key đầy đủ**, rồi mới xét số phần tử trong `IN`. Đếm số dấu phẩy trong danh sách `IN` mà không xem nó nằm trên cột nào là một cách ước lượng sai.

Không nên dùng `IN` tùy ý trên clustering column đầu trong primary key nhiều cột:

```sql
-- Không hợp lệ theo quy tắc IN thông thường của schema này:
-- created_at không phải cột cuối của toàn bộ primary key.
SELECT order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at IN (
      '2026-11-20 09:00:00+0000',
      '2026-11-20 10:00:00+0000'
  );
```

Nếu cần liệt kê **những bộ clustering key đầy đủ**, CQL còn có cú pháp `(created_at, order_id) IN ((t1, id1), (t2, id2))` cho tuple clustering. Đây vẫn là lựa chọn dòng **trong một partition** khi partition key đã cố định, chứ không biến thành nhiều partition.

## 6. Đếm số partition phải định vị: công thức và giới hạn

Với query:

```sql
WHERE tenant_id = :tenant
  AND day_bucket IN (:day1, :day2, :day3)
```

hãy coi `K` là tập các giá trị **partition key đầy đủ** mà câu lệnh biểu diễn. Khi đó:

```text
Số partition-key candidates = |K|

tenant_id = A, day_bucket IN (D1, D2, D3)
K = {(A,D1), (A,D2), (A,D3)}
|K| = 3 (giả sử ba ngày phân biệt)
```

Trong điều kiện các ngày là những giá trị hợp lệ và phân biệt, **ba khóa ứng viên** tương ứng ba partition cần định vị. Nếu một partition chưa có dữ liệu, truy vấn vẫn cần xác định khóa ấy nhưng kết quả trả về không có dòng của partition đó.

### 6.1. Các ví dụ định lượng

| Tình huống | Số khóa partition ứng viên |
| --- | ---: |
| Một tenant và một ngày với `=` | 1 |
| Một tenant và ba ngày trong `IN` | 3 |
| Một tenant và 30 ngày riêng biệt trong `IN` | 30 |
| 4 tenant, mỗi tenant truy vấn 7 ngày bằng các request riêng | Tối đa 28 khóa khác nhau trên **toàn nhóm request** |
| Một tenant, một ngày, 10 `order_id` trong `IN` trên clustering | 1 |
| Một tenant, ba ngày trong `IN` nhưng chỉ có dữ liệu ở hai ngày | 3 khóa ứng viên; 2 partition có dữ liệu |

Ở hàng bốn, con số `4 × 7 = 28` là phép tính **ở cấp ứng dụng** nếu thực sự sinh bốn request, mỗi request có bảy ngày phân biệt; nó **không ám chỉ** rằng có thể viết một truy vấn CQL với hai danh sách `IN` trên composite partition key.

Với nhiều tập truy vấn `Q1, Q2, ...`, ta có thể thống kê theo hai cách:

- **Số lần định vị partition theo yêu cầu:** cộng số partition-key candidates của từng request, kể cả khi cùng khóa được yêu cầu lặp lại.
- **Số partition khác nhau trong toàn đợt:** đếm hợp của các tập khóa đầy đủ `|K1 ∪ K2 ∪ ...|`; khóa lặp chỉ được đếm một lần ở thống kê này.

Đây là hai chỉ số khác nhau. Ví dụ hai request cùng hỏi tenant A/ngày 20 sẽ tạo **hai lượt truy vấn** nhưng chỉ nói đến **một partition duy nhất** xét theo danh tính.

### 6.2. Partition ≠ dòng ≠ node ≠ replica

Không thể suy ra số thông điệp mạng hay số SSTable được đọc chỉ từ số khóa trong `IN`:

| Đại lượng | Ví dụ | Phụ thuộc vào |
| --- | --- | --- |
| **Partition candidates** | 3 khóa `(A, D1..D3)` | Danh sách khóa đầy đủ của truy vấn. |
| **Dòng trả về** | 0, 3 hoặc hàng nghìn dòng | Số dòng ở mỗi partition, điều kiện clustering, tombstones, `LIMIT`. |
| **Node liên quan** | Một hoặc nhiều node | Token placement, topology, replication và routing. |
| **Replica được liên hệ** | Có thể thay đổi theo request | Read consistency level, trạng thái replica, speculative retry, reconciliation. |
| **I/O thực tế** | Nhiều hay ít SSTable/cell | Cache, memtable, SSTable layout, compaction, tombstones. |

Ví dụ, cấu hình replication factor `RF=3` **không có nghĩa** mỗi truy vấn `IN` ba khóa chắc chắn gửi chính xác chín yêu cầu replica. Số replica thực tế được liên hệ phụ thuộc consistency (ví dụ `LOCAL_ONE` khác `LOCAL_QUORUM`), tính khả dụng, cấu hình driver/coordinator và hành vi sửa sai dữ liệu. Tuy nhiên, tăng số partition candidates thường làm tăng công việc phải điều phối.

### 6.3. Ước lượng fan-out trước khi gửi truy vấn

Trong dịch vụ Java, có thể tính trước:

```text
request: tenant=A, days=[20, 21, 22]
distinct days = 3
candidate partition keys = 3

request: tenant=A, days=[20, 20, 21]
distinct days after normalization = 2
candidate partition keys = 2

request batch: 5 tenants x 14 dates
up to 70 distinct full partition keys across the batch
```

Nên **loại giá trị trùng ở client**, kiểm tra giới hạn số ngày/số tenant, và từ chối/điều tiết request quá rộng theo yêu cầu sản phẩm. Việc chuẩn hóa input làm số khóa ước lượng rõ ràng hơn; không cần giả định server sẽ tự tối ưu hoàn hảo mọi danh sách trùng lặp.

## 7. IN và truy vấn phạm vi: khi nào dùng cách nào?

Với bảng `orders_by_tenant_day`, `day_bucket` là partition key, vì vậy:

```sql
-- Hợp lệ: liệt kê những ngày cụ thể.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22');

-- Không phải truy vấn phạm vi hợp lệ trên partition key của bảng này.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket >= '2026-11-20'
  AND day_bucket < '2026-11-23';
```

Phạm vi ngày không chạy theo thứ tự vật lý của những partition được hash từ cặp khóa. `IN` phù hợp khi ứng dụng biết và giới hạn được **một tập bucket cụ thể**, không phải vì nó biến partition key thành cột có chỉ mục phạm vi.

Ngược lại, `created_at` là clustering column đầu tiên. Bên trong một partition, truy vấn theo thời gian là mẫu đọc trực tiếp:

```sql
SELECT created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at >= '2026-11-20 08:00:00+0000'
  AND created_at < '2026-11-20 10:00:00+0000';
```

Kết quả của mẫu này nằm **trong một partition**, vì partition key đầy đủ đã được cố định. Hai dòng trùng timestamp `09:00` vẫn được phân biệt bởi `order_id`.

Chọn mức chia bucket dựa trên nhu cầu: chia quá nhỏ làm các truy vấn lịch sử cần nhiều partition; chia quá lớn tạo hot partition và chi phí đọc/compaction/repair lớn. Không có một bucket “ngày” tối ưu cho mọi hệ thống: phải dựa vào mật độ ghi, kích thước dòng, thời gian giữ dữ liệu và các truy vấn quan trọng.

## 8. LIMIT, PER PARTITION LIMIT và vấn đề phân trang

Hai giới hạn sau có phạm vi khác nhau:

```sql
-- Tối đa 2 dòng cho cả kết quả CQL.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
LIMIT 2;

-- Tối đa 1 dòng từ mỗi partition được truy vấn.
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

Với dữ liệu mẫu:

- Truy vấn `LIMIT 2` trả **không quá hai dòng tổng cộng**, không bảo đảm đó là “đơn mới nhất của cả ba ngày” nếu không có cơ chế hợp nhất thứ tự toàn cục phù hợp.
- Truy vấn `PER PARTITION LIMIT 1` cho phép tối đa **một dòng mỗi ngày**, nên từ ba partition có dữ liệu có thể trả ba dòng (mỗi partition một dòng).
- Có thể dùng đồng thời `PER PARTITION LIMIT 1 LIMIT 2`: khi đó **cả hai giới hạn** cùng áp dụng, cuối cùng không quá hai dòng tổng cộng.

**Cảnh báo thiết kế:** `ORDER BY` của Cassandra dựa trên clustering columns, không tương đương `ORDER BY created_at DESC` toàn cục trên mọi tenant và ngày. Khi tìm “20 đơn mới nhất toàn tenant” qua nhiều bucket, cần định nghĩa rõ cách ghép kết quả, số partition được phép quét và chiến lược cursor/aggregation. Không nên mặc định `IN` + `LIMIT 20` giải quyết bài toán sắp xếp nhiều partition.

Java driver có **page size** và **paging state**; chúng khác cả `LIMIT` lẫn `PER PARTITION LIMIT`:

- **Page size** kiểm soát lượng dữ liệu được fetch qua từng đợt của cùng truy vấn, không quyết định số partition mà điều kiện `IN` phải xét.
- **Paging state** dùng để tiếp tục một truy vấn tương ứng với cùng tham số; nó không tự cung cấp thứ tự toàn cục hay snapshot bất biến giữa những lần đọc.
- Không có `OFFSET` như SQL để nhảy bỏ N dòng một cách hiệu quả. Nếu nghiệp vụ yêu cầu lịch sử dài và phân trang ổn định, nên xác định cursor và mô hình lưu trữ ngay từ khi thiết kế bảng.

## 9. Bao nhiêu giá trị IN là quá nhiều?

Không có ngưỡng số phần tử `IN` “an toàn cho mọi cluster”. Tác động phụ thuộc kích thước từng partition, số replica, cách đặt token trên node, consistency level, cache, số SSTable/tombstone và số request đồng thời.

Đối chiếu các trường hợp:

| Tình huống | Nhận xét về cách dùng |
| --- | --- |
| Tenant A xem đơn của 2–3 ngày đã chọn | `IN` với danh sách ngắn có thể là cách đơn giản, dễ dự đoán. |
| Tenant A yêu cầu 90 ngày, mỗi ngày một partition | Truy vấn có fan-out 90 partition; cần đo độ trễ và cân nhắc chia thành các đợt truy vấn có kiểm soát. |
| API nhận hàng nghìn ngày không giới hạn | Rủi ro fan-out, payload, timeout, áp lực coordinator và quá tải cluster. |
| Hai `order_id` trong một partition cụ thể | `IN` trên clustering column cuối chỉ định vị một partition; chi phí phân tán khác với hai ngày. |
| Truy vấn luôn cần dữ liệu mọi ngày của một tháng | Có thể thiết kế thêm bảng theo bucket tháng hoặc summary, tùy mật độ dữ liệu và mức tải. |

**Gợi ý thiết kế vận hành:**

1. Giới hạn độ dài danh sách `IN` ở API bằng một con số phù hợp sau khi benchmark.
2. Loại ngày trùng, kiểm tra ranh giới tenant/date và từ chối input không hợp lệ trước khi query.
3. Giới hạn số request đồng thời nếu ứng dụng chia danh sách ngày thành nhiều truy vấn `=`; không tạo hàng trăm truy vấn song song vô điều kiện.
4. Đo p95/p99 latency, coordinator read latency, timeout, retries và read amplification bằng tracing/metrics; kiểm tra partition size, tombstone và hoạt động compaction.
5. Chọn replication và consistency theo cam kết về độ mới/khả dụng; `IN` không thay đổi bản chất các lựa chọn ấy.

Một truy vấn `IN` lớn và hàng trăm truy vấn `=` cùng lúc đều có thể gây quá tải. Quyết định nên dựa trên bằng chứng hiệu năng và khả năng quản lý concurrency, không chỉ trên số câu CQL.

## 10. Java driver: truy vấn danh sách partition có kiểm soát

Giả sử `CqlSession session` đã kết nối vào keyspace `cassandra_in_lab`; ví dụ dưới đây dùng Java Driver 4.x và Java 15+ để hỗ trợ text blocks.

### 10.1. Danh sách có hai ngày cố định

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

UUID tenantId = UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");

PreparedStatement prepared = session.prepare("""
    SELECT day_bucket, created_at, order_id, status
    FROM orders_by_tenant_day
    WHERE tenant_id = ?
      AND day_bucket IN (?, ?)
    """);

BoundStatement bound = prepared.bind(
    tenantId,
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-21")
).setPageSize(100);

ResultSet resultSet = session.execute(bound);
for (Row row : resultSet) {
    System.out.printf("%s | %s | %s%n",
        row.getLocalDate("day_bucket"),
        row.getUuid("order_id"),
        row.getString("status"));
}
```

Trong ví dụ này, `IN (?, ?)` có hai bind markers tương ứng hai ngày. Driver ánh xạ CQL `uuid` thành `UUID` và CQL `date` thành `LocalDate`. `setPageSize(100)` điều chỉnh quá trình fetch; nó **không thay** `LIMIT` và không làm truy vấn chỉ chạm một partition.

Số placeholder phải phù hợp với số phần tử. Khi số ngày thay đổi theo request, ứng dụng có thể chọn số lượng placeholder tương ứng với một số trường hợp giới hạn, hoặc dùng cơ chế bind list cho `IN` nếu driver/CQL đang dùng hỗ trợ, hoặc tách thành các truy vấn bằng `=`. Không nối trực tiếp input người dùng vào CQL như một chuỗi danh sách giá trị.

### 10.2. Tính trước fan-out và xử lý input

```java
import java.time.LocalDate;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

List<LocalDate> requestedDays = List.of(
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-20"),
    LocalDate.parse("2026-11-21")
);

Set<LocalDate> uniqueDays = new LinkedHashSet<>(requestedDays);
int candidatePartitions = uniqueDays.size(); // 2 với tenant cố định

if (uniqueDays.isEmpty() || candidatePartitions > 14) {
    throw new IllegalArgumentException("Khoang ngay khong hop le");
}

// Tiếp theo: tạo truy vấn tham số hóa tương ứng với uniqueDays
// hoặc gửi các point-partition reads, với concurrency được giới hạn.
```

Giới hạn `14` ở đây chỉ là **ví dụ chính sách API**, không phải giới hạn cứng của Apache Cassandra. Với một tenant cố định, `uniqueDays.size()` chính là số full partition keys **ứng viên**; trong triển khai nhiều tenant, tính theo các cặp `(tenant_id, day_bucket)` duy nhất.

**Không giả định mỗi page của Java driver ứng với một partition.** Truy vấn nhiều partition có thể tiếp tục qua nhiều trang; ánh xạ từng record cần mang theo `day_bucket` và các trường khóa để ghép dữ liệu đúng tenant/ngày. Nếu cần một bảng xếp hạng toàn cục theo `created_at`, phải có chiến lược hợp nhất và giới hạn dữ liệu rõ ràng.

## 11. Những lỗi thường gặp

| Nhầm lẫn | Điều đúng cần nhớ | Cách xử lý |
| --- | --- | --- |
| `IN (D1,D2,D3)` chỉ đọc một partition vì đã biết `tenant_id` | Composite partition key gồm **tenant và ngày**; mỗi ngày là một full key khác nhau. | Đếm các cặp `(tenant_id, day_bucket)`. |
| `IN` có 3 giá trị thì kết quả luôn 3 dòng | Mỗi partition chứa số dòng khác nhau, có thể rỗng. | Phân biệt số khóa ứng viên với số dòng. |
| `IN` trên `order_id` giống `IN` trên `day_bucket` | `order_id` là clustering column cuối; `day_bucket` là partition key. | Xác định vị trí của `IN` trong schema. |
| `tenant_id IN (...) AND day_bucket = D` được hỗ trợ như `day_bucket IN (...)` | `tenant_id` không là thành phần cuối của composite partition key. | Tạo các truy vấn theo tenant cụ thể hoặc bảng truy vấn khác. |
| `day_bucket >= D1 AND day_bucket < D2` là range scan trong tenant | `day_bucket` là partition key, các partition được phân phối bằng token. | Liệt kê bucket hữu hạn hoặc thiết kế lược đồ khác. |
| `LIMIT 10` đồng nghĩa chỉ liên hệ tối đa 10 partition | `LIMIT` giới hạn **dòng kết quả**, không thay tập khóa ứng viên của `IN`. | Giới hạn danh sách key và bucket ngay ở request. |
| `PER PARTITION LIMIT 1` có nghĩa tổng chỉ một dòng | Nó giới hạn **mỗi partition**; nhiều partition có thể trả nhiều dòng. | Kết hợp thêm `LIMIT` nếu cần giới hạn tổng. |
| `RF=3` nên truy vấn 10 partition luôn tạo đúng 30 read requests | Replica được liên hệ còn phụ thuộc consistency và cơ chế truy vấn. | Theo dõi driver/coordinator metrics thay vì suy ra số request cứng. |
| `IN` tự sắp xếp toàn cục theo clustering | Clustering order có ý nghĩa trong từng partition. | Thiết kế merge/cursor hoặc bảng riêng theo thứ tự cần. |
| Thêm `ALLOW FILTERING` giải quyết truy vấn thiếu partition key | Có thể buộc quét dữ liệu với chi phí khó dự đoán. | Thiết kế lại cách truy cập, không dùng lọc toàn cluster cho API nóng. |

## 12. Bài tập thực hành có đáp án

### Bài 1: Đếm partition của IN trên khóa ghép

Cho khóa `PRIMARY KEY ((tenant_id, day_bucket), created_at, order_id)`, một tenant cố định, và danh sách ngày `[20, 21, 22]` tháng 11/2026. Hỏi truy vấn nhắm tới bao nhiêu partition?

**Đáp án:** **3 partition ứng viên**, tương ứng `(tenant A, 20)`, `(tenant A, 21)`, `(tenant A, 22)`. Số dòng có thể nhiều hơn ba. Viết CQL:

```sql
SELECT day_bucket, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22');
```

Với dữ liệu mẫu, kết quả có **4 dòng** từ **3 partition**, không phải ba dòng.

### Bài 2: IN trên clustering column

Với tenant A ngày 20/11, hãy lấy hai đơn lúc `09:00` có ID kết thúc bằng `...0011` và `...0012`. Hỏi có bao nhiêu partition?

**Đáp án:** Một partition, hai dòng:

```sql
SELECT created_at, order_id, status
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket = '2026-11-20'
  AND created_at = '2026-11-20 09:00:00+0000'
  AND order_id IN (
      00000000-0000-4000-8000-000000000011,
      00000000-0000-4000-8000-000000000012
  );
```

### Bài 3: Chọn LIMIT hay PER PARTITION LIMIT

Yêu cầu lấy tối đa **một đơn từ mỗi ngày** trong ba ngày đã biết của tenant A.

**Đáp án:**

```sql
SELECT day_bucket, created_at, order_id
FROM orders_by_tenant_day
WHERE tenant_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND day_bucket IN ('2026-11-20', '2026-11-21', '2026-11-22')
PER PARTITION LIMIT 1;
```

Truy vấn trả tối đa **ba dòng** với ba partition đã biết. Không thay `PER PARTITION LIMIT 1` bằng `LIMIT 1` nếu muốn giữ tối đa một dòng **cho từng ngày**.

### Bài 4: Fan-out từ nhiều tenant

Một công cụ kiểm tra đọc **5 tenant**, mỗi tenant có **7 ngày phân biệt**, mỗi tenant được truy vấn riêng với `IN` bảy ngày. Hỏi có thể có bao nhiêu full partition keys khác nhau?

**Đáp án:** `5 × 7 = 35` full partition keys khác nhau, nếu năm tenant thực sự khác nhau; đây là tổng ở cấp **nhiều request**, không phải một câu `WHERE tenant_id IN (...) AND day_bucket IN (...)`. Số partition có dữ liệu, số dòng trả về và số replica liên hệ phải được đo/quan sát riêng.

### Bài 5: Phản biện một “tối ưu” sai

Đề xuất: “Đổi `day_bucket IN (D1, ..., D100)` thành cùng câu `IN` nhưng thêm `LIMIT 10`, khi đó Cassandra chỉ còn đọc tối đa 10 partition.”

**Đáp án:** Sai. `LIMIT` giới hạn số **dòng kết quả**, không biến 100 khóa phân vùng ứng viên thành 10 khóa. Nếu cần giảm fan-out, hãy thay đổi danh sách bucket cần tra cứu, chia request thành những đợt được giới hạn, hoặc thiết kế lại bảng phục vụ truy vấn thường xuyên.

## 13. Checklist trước khi dùng IN trong API

1. **Đọc đúng primary key:** xác định rõ thành phần nào thuộc partition key, thành phần nào thuộc clustering; đừng nhìn tên cột rồi đoán.
2. **Kiểm tra vị trí IN:** `IN` có nằm trên cột cuối của partition key hoặc cột cuối của full primary key theo cú pháp hỗ trợ không? Các thành phần trước đã có điều kiện thích hợp chưa?
3. **Ước lượng fan-out:** sau khi chuẩn hóa input, có bao nhiêu full partition-key candidates? Bao nhiêu candidate xuất phát từ tất cả các request đồng thời?
4. **Kiểm soát khối lượng:** có chặn danh sách quá dài, partition quá lớn, page size hoặc concurrency vượt mức vận hành không?
5. **Hiểu output:** dùng `LIMIT` hay `PER PARTITION LIMIT` theo ý nghĩa nào? Có cần kết quả sắp xếp toàn cục khi các dòng ở nhiều partition không?
6. **Khả năng phân tán:** replication, consistency, trạng thái replica, compaction/repair, tombstones và retries có thể tác động độ trễ thế nào? Đã đo p95/p99 latency chưa?
7. **Tích hợp Java:** đã bind đúng kiểu `UUID`/`LocalDate`, quản lý paging state và xử lý timeout phù hợp với query size chưa?

Điểm cốt lõi: **đếm các full partition keys** mà truy vấn thực sự cần tìm. `IN` trên thành phần cuối của composite partition key có thể tạo **nhiều partition reads**; `IN` trên clustering key cuối thường vẫn nằm **trong một partition**. Sự khác biệt này quan trọng hơn số phần tử trong danh sách `IN` khi thiết kế CQL cho hệ thống Cassandra phân tán.

## Tài liệu tham khảo

- [Apache Cassandra Documentation — Data Manipulation: WHERE, IN, ORDER BY và LIMIT](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Definition: Primary Key và Clustering Columns](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html)
- [Apache Cassandra Documentation — CQL Single File Reference](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/cql_singlefile.html)
- [Apache Cassandra Java Driver 4.x — Paging](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
