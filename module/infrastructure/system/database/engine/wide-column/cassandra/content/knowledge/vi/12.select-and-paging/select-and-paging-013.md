# Page size, số hàng trả về và dữ liệu đang thay đổi trong Apache Cassandra

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Phân biệt **page size của Cassandra**, **số hàng thực sự có trong một page**, `LIMIT` và kích thước trang hiển thị trong API.
2. Giải thích tại sao một page có ít hàng hơn `fetch size` không nhất thiết có nghĩa đã hết dữ liệu.
3. Dùng `paging state` và tín hiệu `hasMorePages()` đúng cách, kể cả khi một trang có rất ít hoặc không có hàng phù hợp.
4. Phân tích tác động của **INSERT, DELETE, UPDATE, TTL và sự khác biệt giữa replica** trong lúc khách hàng duyệt các trang.
5. Phân biệt phân trang theo giao thức với **keyset pagination** trên clustering key và giới hạn bởi thời điểm `asOf`.
6. Thiết kế Java API tránh bỏ sót các hàng chưa xử lý, tránh gửi token sai truy vấn/tenant và tránh biến page size thành phép quét vô hạn.
7. Xây kịch bản thử nghiệm có thay đổi dữ liệu, đo hiệu năng và xác định những bảo đảm ứng dụng có thể công bố một cách chính xác.

Bài thuộc chương **SELECT và phân trang** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Apache Cassandra là cơ sở dữ liệu wide-column phân tán: partition key định tuyến tới partition và replica, clustering columns sắp thứ tự các hàng trong partition, còn replication, consistency, TTL, compaction và repair ảnh hưởng dữ liệu mà mỗi lần đọc quan sát được. Vì vậy, phân trang không chỉ là bài toán giao diện “mỗi lần 20 dòng”, mà còn là **một chuỗi thao tác đọc trên dữ liệu có thể thay đổi giữa các lần gọi**.

## 1. Một trang hiển thị không đồng nghĩa một trang Cassandra

Giả sử màn hình lịch sử hoạt động hiển thị **20 sự kiện mỗi lần**. Có ít nhất bốn đại lượng:

| Khái niệm | Ai quyết định? | Ý nghĩa |
| --- | --- | --- |
| **Page size / fetch size** | Java Driver, ví dụ `setPageSize(20)` | Số hàng **mục tiêu** trong một lần fetch ở native protocol. |
| **Hàng của page thực nhận** | Cassandra/driver tại lần fetch | Có thể khác page size được đề nghị. |
| **`LIMIT 100`** | Câu CQL | Trần tổng số hàng mà **toàn truy vấn** được phép trả về. |
| **20 mục trên trang UI** | Hợp đồng HTTP và logic ứng dụng | Số mục cần trình bày, có thể cần xử lý/buffer ngoài ranh giới page giao thức. |

Ví dụ:

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = ?
  AND event_day = ?
LIMIT 100;
```

Với `setPageSize(20)`, nếu có 63 hàng khớp, client có thể nhận các page liên tiếp cho đến hết **63 hàng**, không phải chỉ 20. `LIMIT 100` không buộc server tạo 100 hàng, và cũng không nói rằng **mỗi** page có 100 hàng.

**Page size được xem là mục tiêu/hint, không phải hợp đồng chính xác về số hàng**. Server có thể trả ít hàng hơn dự kiến, ví dụ do cách thực thi, lọc, giới hạn response hoặc đặc điểm dữ liệu. Số hàng một page và dấu hiệu **còn trang sau** là hai thông tin cần xét riêng.

> Quy tắc quan trọng: khi dùng Java Driver `AsyncResultSet`, **`hasMorePages()` mới là tín hiệu tiếp tục**, không phải phép so sánh `currentPage().size() < pageSize`.

## 2. Phân trang diễn ra trong truy vấn phân tán như thế nào?

Hãy hình dung một truy vấn theo full partition key:

```text
HTTP Client
    |
    | GET /accounts/A/events?day=2026-11-20
    v
Java API / Cassandra Java Driver
    |
    | CQL + bound values + page size
    v
Coordinator --------> Replica(s) theo token và consistency
    |                         |
    |                         +-- memtable / SSTable
    |                         +-- TTL / tombstones / reconciliation
    |                         +-- clustering order
    v
Page 1: các Row + opaque paging state S1
    |
    | tiếp tục với cùng truy vấn + S1
    v
Page 2: các Row + paging state S2 hoặc hết kết quả
    |
    v
...
```

Page size thường giúp **giảm số hàng và byte cần truyền trong một đợt fetch**, không thay thế điều kiện định vị dữ liệu. Nếu query thiếu partition key hoặc dùng `ALLOW FILTERING` trên nhiều partition, chia response thành trang nhỏ **không làm mất chi phí quét rộng**.

Một paging state là vị trí tiếp tục do Cassandra/driver quản lý cho **câu truy vấn cụ thể**. Nó không phải snapshot của bảng, không phải offset có thể tự sửa, và không phải khóa phân vùng của hàng cuối.

### 2.1. Ba lớp chi phí khác nhau

| Đại lượng | Câu hỏi trả lời | Điều thường kiểm soát nó |
| --- | --- | --- |
| Số partition ứng viên | Cần tìm bao nhiêu partition? | `WHERE` trên full partition key, danh sách `IN` hữu hạn |
| Dòng/giá trị phải kiểm tra | Cần xử lý bao nhiêu dữ liệu để chọn hàng hợp lệ? | Clustering range, TTL, tombstone, filtering, SSTable |
| Hàng/byte truyền về từng page | Client nhận bao nhiêu dữ liệu trong đợt này? | Projection, page size, giới hạn thực thi của server |

Đừng tính chi phí đọc bằng công thức `pageSize × sốPage` rồi cho rằng đó là số cell vật lý Cassandra đã đọc. Số hàng kết quả không bao gồm các tombstone hoặc hàng bị loại bởi điều kiện lọc.

## 3. Lab CQL: dữ liệu đủ để thấy ba trang

### 3.1. Tạo keyspace và bảng

Giả sử ứng dụng lưu hoạt động của **một account trong một ngày**, có các sự kiện trùng timestamp nhưng khác ID.

```sql
-- SimpleStrategy/RF=1 chỉ dành cho lab một node;
-- production đa node dùng chiến lược replication phù hợp topology.
CREATE KEYSPACE IF NOT EXISTS cassandra_page_mutation_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

USE cassandra_page_mutation_lab;

CREATE TABLE IF NOT EXISTS events_by_account_day (
    account_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((account_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

| Thành phần | Vai trò | Ý nghĩa khi paging |
| --- | --- | --- |
| `(account_id, event_day)` | Composite partition key | Một ngày của một account là một partition. |
| `occurred_at` | Clustering column thứ nhất | Duyệt thời gian từ mới nhất tới cũ nhất. |
| `event_id` | Clustering column thứ hai | Tạo thứ tự xác định cho các sự kiện cùng timestamp. |
| `event_type`, `summary` | Regular columns | Chứa nội dung hiển thị, không quyết định vị trí. |

### 3.2. Nạp bảy sự kiện vào partition chính

```sql
-- Account A, ngày 20/11: 7 dòng.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 08:00:00+0000',
    00000000-0000-4000-8000-000000000001,
    'LOGIN', 'Dang nhap'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 09:00:00+0000',
    00000000-0000-4000-8000-000000000002,
    'VIEW', 'Xem san pham'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000003,
    'CLICK', 'Mo chi tiet'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 10:00:00+0000',
    00000000-0000-4000-8000-000000000004,
    'PAY', 'Thanh toan'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 12:00:00+0000',
    00000000-0000-4000-8000-000000000005,
    'SHIP', 'Da gui hang'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 13:00:00+0000',
    00000000-0000-4000-8000-000000000006,
    'DELIVER', 'Da giao'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 14:00:00+0000',
    00000000-0000-4000-8000-000000000007,
    'LOGOUT', 'Dang xuat'
);

-- Account A, ngày 21: partition thứ hai có 2 dòng.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 09:00:00+0000',
    00000000-0000-4000-8000-000000000008,
    'LOGIN', 'Ngay tiep theo'
);

INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21 10:00:00+0000',
    00000000-0000-4000-8000-000000000009,
    'VIEW', 'Xem bao cao'
);

-- Account B, ngày 20: partition thứ ba có 1 dòng.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    22222222-2222-4222-8222-222222222222,
    '2026-11-20', '2026-11-20 07:00:00+0000',
    00000000-0000-4000-8000-000000000010,
    'LOGIN', 'Account B'
);
```

Nếu bảng mới và chỉ có dữ liệu mẫu, tổng có **10 dòng thuộc ba partition**. Partition chính account A/ngày 20 có đúng **bảy dòng**, thứ tự mặc định:

| Vị trí | Thời gian UTC | `event_id` (đuôi) | `event_type` |
| ---: | --- | --- | --- |
| 1 | 14:00 | `...0007` | `LOGOUT` |
| 2 | 13:00 | `...0006` | `DELIVER` |
| 3 | 12:00 | `...0005` | `SHIP` |
| 4 | 10:00 | `...0004` | `PAY` |
| 5 | 10:00 | `...0003` | `CLICK` |
| 6 | 09:00 | `...0002` | `VIEW` |
| 7 | 08:00 | `...0001` | `LOGIN` |

Hai sự kiện lúc 10:00 được phân biệt bởi `event_id`. Nếu chạy lại cùng `INSERT` với cùng full primary key, Cassandra thực hiện upsert, không sinh thêm hàng trùng khóa. Các thay đổi được thực hành ở phần sau sẽ làm kết quả khác với bảng dữ liệu gốc này.

## 4. Page size 3 có đồng nghĩa ba hàng một trang?

### 4.1. Chạy thử với cqlsh

```sql
USE cassandra_page_mutation_lab;

-- Lệnh điều khiển hiển thị của cqlsh, không phải cú pháp SELECT.
PAGING 3;

SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC;

PAGING OFF;
```

Trong **mô phỏng lý tưởng**, nếu server trả đúng ba hàng cho các trang đầy:

```text
Trang 1: 14:00/0007, 13:00/0006, 12:00/0005
Trang 2: 10:00/0004, 10:00/0003, 09:00/0002
Trang 3: 08:00/0001
           |
           +-- hết kết quả
```

Sơ đồ giúp theo dõi dữ liệu của lab, **không phải cam kết native protocol luôn chia 3/3/1**. Driver/server có thể trả số lượng khác kích thước mục tiêu. Client cần xử lý số dòng thực nhận và xem còn paging state hay không.

### 4.2. Phân biệt “đủ N hàng”, “ít hơn N” và “hết dữ liệu”

Giả sử `pageSize = 3`. Một trang có thể biểu diễn:

| Hàng nhận trong page | `hasMorePages()` | Cách xử lý |
| ---: | --- | --- |
| 3 | `true` | Xử lý cả ba, cho phép fetch tiếp. |
| 2 | `true` | **Vẫn còn trang sau**; không tự kết luận hết. |
| 1 | `false` | Trang cuối trong quá trình đọc hiện tại. |
| 0 | `true` | Trang rỗng nhưng **có thể còn dữ liệu**; xử lý chính sách fetch tiếp có giới hạn. |
| 0 | `false` | Kết thúc, không có thêm trang. |

Trường hợp page rỗng nhưng còn state có thể xuất hiện ở những đường thực thi phức tạp như filtering hoặc trường hợp có nhiều dữ liệu không còn sống. Nó **không phải đặc điểm cố định** của lab đơn giản chỉ gồm bảy hàng còn sống.

**Không dùng quy tắc sai:**

```java
// SAI: kích thước một page không chứng minh đã hết toàn truy vấn.
if (items.size() < requestedPageSize) {
    return "NO_MORE_DATA";
}
```

Đúng hơn, khi điều khiển paging bằng `AsyncResultSet`, xét `hasMorePages()` và paging state tương ứng sau khi **xử lý hết trang hiện tại**.

## 5. LIMIT, PER PARTITION LIMIT và số hàng thực trả

### 5.1. LIMIT là trần kết quả của toàn câu SELECT

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 5;
```

Trên dữ liệu gốc, trả tối đa **năm dòng**: `0007, 0006, 0005, 0004, 0003`. Nếu page size mục tiêu là ba, một phép chia lý tưởng có thể là **3 + 2**, nhưng chỉ cần dựa vào giới hạn tổng và tín hiệu kết thúc thực tế, không dựa vào phép chia lý tưởng để tự suy state.

Nếu `LIMIT 20` trong cùng partition chỉ có bảy dòng, toàn truy vấn vẫn trả **bảy dòng**, không phải hai mươi.

Một điểm dễ sai khi xây API HTTP: nếu câu CQL có `LIMIT 5`, dùng paging state để tiếp tục **cùng truy vấn** không có nghĩa trang HTTP kế tiếp lại được quyền trả thêm năm dòng nữa ngoài giới hạn tổng. Muốn “mỗi trang HTTP tối đa năm” qua nhiều request, phải thiết kế semantics và cách truy vấn cho phù hợp; đừng nhầm `LIMIT` toàn truy vấn với giới hạn mỗi network page.

### 5.2. PER PARTITION LIMIT dùng khi đọc nhiều partition

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2;
```

Theo dữ liệu gốc, có hai partition ngày 20 và 21, mỗi partition đóng góp tối đa hai hàng, nên tổng **bốn dòng**. Chúng là:

| Partition | Hàng giữ lại |
| --- | --- |
| Account A/ngày 20 | `14:00/0007` và `13:00/0006` |
| Account A/ngày 21 | `10:00/0009` và `09:00/0008` |

**Đây không phải thứ tự thời gian toàn cục**, và cũng không có bảo đảm một network page ứng với chính xác một partition. Giới hạn mỗi partition hoạt động ở cấp kết quả CQL, không phải “đếm lại từ đầu cho từng page fetch”.

Kết hợp:

```sql
SELECT event_day, occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day IN ('2026-11-20', '2026-11-21')
PER PARTITION LIMIT 2
LIMIT 3;
```

thì không partition nào đóng góp quá hai hàng và **toàn kết quả tối đa ba hàng**; không được khẳng định chắc hàng thứ ba thuộc ngày nào nếu truy vấn không có một hợp đồng thứ tự toàn cục thích hợp.

### 5.3. Số trang chỉ có thể ước lượng khi biết giả định

Giả sử không có ghi/xóa, không filtering, `R` là số hàng kết quả và mọi trang (trừ trang cuối) thực sự có `F` hàng:

```text
Số trang lý tưởng P = ceil(R / F)

R = 7, F = 3  ->  P = ceil(7/3) = 3
R = 5, F = 3  ->  P = ceil(5/3) = 2
```

Đây **không phải công thức API bảo đảm page count**. Trên dữ liệu biến động và page size là mục tiêu, tổng `R` có thể đổi giữa các lần fetch, và số page phụ thuộc cách server trả dữ liệu.

Không chạy `COUNT(*)` toàn bảng chỉ để tạo “Tổng 123.456 trang”: trên Cassandra phân tán, phép đếm có thể rất đắt và không bảo đảm một snapshot phù hợp với các trang được đọc sau đó.

## 6. Dữ liệu thay đổi trong lúc phân trang: bốn tình huống

Giả sử tại thời điểm `T0`, client đã lấy page đầu gồm:

```text
Page 1 ở T0:
  14:00/0007 (LOGOUT)
  13:00/0006 (DELIVER)
  12:00/0005 (SHIP)

State S1: vị trí dùng để tiếp tục sau page 1
```

Sau đó client gửi request với `S1` ở `T1`. Giữa `T0` và `T1` có thể đã xảy ra một số thay đổi.

### 6.1. INSERT một hàng mới đứng *trước* vị trí đã đi qua

```sql
-- Minh họa trong lab sau khi đã lấy page 1.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 15:00:00+0000',
    00000000-0000-4000-8000-000000000011,
    'REVIEW', 'Moi xuat hien'
);
```

Vì thứ tự clustering là giảm dần, hàng lúc `15:00` đứng **trước** `14:00`. Một truy vấn đọc mới từ đầu sẽ thấy nó đầu tiên, nhưng một chuỗi paging đã đi qua đầu danh sách **không có bảo đảm** sẽ quay lại lấy hàng mới ấy.

**Hệ quả:** trạng thái “đã xem hết lịch sử bằng cách nhấn Xem thêm” không đồng nghĩa đã xem tất cả sự kiện sinh ra trong khoảng thời gian người dùng đang đọc. Nếu cần các sự kiện mới nhất, client thường phải làm mới từ đầu hoặc có luồng cập nhật mới riêng.

### 6.2. INSERT một hàng vào vùng *chưa đọc*

```sql
-- Một sự kiện ghi muộn với timestamp nằm giữa 12:00 và 10:00.
INSERT INTO events_by_account_day
    (account_id, event_day, occurred_at, event_id, event_type, summary)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20', '2026-11-20 11:00:00+0000',
    00000000-0000-4000-8000-000000000012,
    'BACKFILL', 'Su kien ghi muon'
);
```

Hàng lúc `11:00` nằm trong vùng dữ liệu mà chuỗi paging lý tưởng sắp duyệt. **Nó có thể xuất hiện ở trang kế tiếp**, nhưng điều đó phụ thuộc vị trí continuation, dữ liệu được các replica nhìn thấy và thời điểm fetch. Không có snapshot cố định bảo đảm kết quả **giống bảng tại T0**.

Điều này cũng có nghĩa “đóng băng ngày” bằng điều kiện chỉ đọc `event_day = '2026-11-20'` **không** ngăn được ghi muộn vào cùng ngày.

### 6.3. DELETE một hàng chưa đọc

```sql
-- Xóa một hàng có full primary key trong lab.
DELETE FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 10:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000004;
```

Hàng `PAY/0004` có thể không còn xuất hiện ở page tiếp theo sau khi xóa được quan sát. Page đó có thể ngắn hơn, hoặc các hàng khác được kéo lên theo số trang trả về. Không suy rằng sau page 1 sẽ luôn là bộ hàng cố định `0004,0003,0002`.

Xóa Cassandra tạo tombstone; trước khi compaction có thể phải xử lý các dấu xóa khi đọc. **Số hàng còn sống ít đi không nhất thiết làm công việc I/O giảm theo tỷ lệ**.

### 6.4. UPDATE cột thường hoặc thay đổi khóa sắp xếp

```sql
-- Cập nhật cột thường của một hàng chưa đọc.
UPDATE events_by_account_day
SET summary = 'Da sua mo ta'
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at = '2026-11-20 09:00:00+0000'
  AND event_id = 00000000-0000-4000-8000-000000000002;
```

Các cột khóa của `VIEW/0002` không đổi, nhưng nội dung `summary` mà page sau nhận có thể là giá trị mới, không phải giá trị ở `T0`.

Nếu cần “đổi timestamp” (là clustering column), Cassandra **không cập nhật primary key tại chỗ** theo nghĩa đổi thứ tự của cùng hàng. Ứng dụng phải tạo một hàng ở khóa mới và xử lý hàng cũ; từ góc nhìn phân trang, đây là **thay đổi tập hàng và thứ tự**, có thể khiến một logic event được nhìn thấy khác với kỳ vọng nếu API không có chính sách ID/phiên bản.

### 6.5. Bảng tóm tắt các tình huống

| Biến động sau page 1 | Điều có thể xảy ra ở page tiếp | Bảo đảm không nên hứa |
| --- | --- | --- |
| INSERT hàng mới hơn tất cả hàng đã xem | Hàng mới không xuất hiện trong những page còn lại | “Duyệt tiếp chắc chắn thấy mọi insert mới.” |
| INSERT ghi muộn vào vùng chưa đọc | Hàng mới có thể tham gia kết quả tiếp | “Các trang sau chỉ có dữ liệu từ T0.” |
| DELETE hàng chưa xem | Hàng biến mất hoặc số hàng/page thay đổi | “Trang sau chứa cố định ba ID dự kiến.” |
| UPDATE regular column | Giá trị trả về có thể là phiên bản mới | “Cùng một snapshot dữ liệu qua mọi trang.” |
| TTL hết hạn | Hàng/cell không còn được trả theo trạng thái mới | “Page size đảm bảo đủ N hàng sống.” |
| Replica hội tụ ở thời điểm khác nhau | Các lần đọc có thể quan sát trạng thái khác nhau | “Cùng query là đọc nhất quán tại một thời điểm toàn cluster.” |

**Kết luận:** paging state giúp **tiếp tục công việc duyệt**, không đóng băng nội dung của cơ sở dữ liệu.

## 7. TTL, tombstone và vì sao page có thể rất ngắn

### 7.1. Hàng hết TTL và dấu xóa

Trong Cassandra, TTL có thể làm dữ liệu hết hiệu lực; xóa dữ liệu thường đi qua cơ chế tombstone. Server phải xử lý các thông tin đó để chỉ trả về những hàng/giá trị còn hợp lệ.

Ví dụ khái niệm:

```text
Partition / clustering slice có 50 vị trí hoặc phiên bản dữ liệu
   |
   +-- 42 bản ghi/giá trị đã hết hạn, bị xóa hoặc bị che bởi tombstone
   +-- 8 hàng còn sống, khớp query
   |
   v
Response có tối đa 8 hàng hữu ích từ lát cắt này
```

Đó là **sơ đồ minh họa**, không phải cam kết nội bộ “50 vị trí chắc chắn chỉ tạo 8 hàng”. Trên thực tế, storage engine có thể cần kiểm tra rất nhiều cell/SSTable để tìm được hàng sống; một page với rất ít dòng vẫn có thể chậm hoặc sinh cảnh báo tombstone.

Không dùng:

```text
Số hàng trả = 3
=> Cassandra chỉ đọc 3 hàng trên đĩa       (sai)
=> Chắc chắn đã tới cuối kết quả           (sai)
```

Muốn biết còn trang sau phải xem trạng thái paging. Muốn biết chi phí đọc phải xem metrics/tracing, không suy từ số hàng kết quả.

### 7.2. Filtering và trang rỗng

Nếu query có một điều kiện trên cột thường được thực thi bằng `ALLOW FILTERING`, rất nhiều hàng ứng viên có thể bị loại trước khi tạo result rows. Tùy phiên bản và đường thực thi, có thể gặp page chứa **không có hàng phù hợp nhưng vẫn còn paging state**.

Vì vậy, code async nên dùng một chính sách rõ:

1. Xử lý tất cả hàng trong `currentPage()`, kể cả khi rỗng.
2. Kiểm tra `hasMorePages()` để biết còn continuation.
3. Chỉ fetch trang tiếp theo khi endpoint/job cần tiếp và **còn trong ngân sách thời gian, trang, bytes và số request**.
4. Nếu liên tiếp gặp page rỗng do một truy vấn lọc quá rộng, **không lặp vô hạn**; dừng theo budget và đánh giá lại schema/query.

Tốt hơn hết, thiết kế truy vấn theo partition key và clustering range để tránh phụ thuộc một đường lọc dữ liệu quá rộng.

### 7.3. Compaction và repair không tạo snapshot

Compaction giúp tổ chức SSTable và có thể loại bỏ dữ liệu đã xóa khi thỏa điều kiện an toàn; repair giúp replica hội tụ. Hai cơ chế ảnh hưởng read amplification và dữ liệu quan sát, nhưng **không biến một chuỗi SELECT có paging thành transaction snapshot**.

Nếu cluster đang compaction/repair hoặc có replica chậm, tail latency giữa các page có thể khác nhau đáng kể. Không tối ưu chỉ bằng việc “đặt page size bằng 1” rồi kỳ vọng truy vấn luôn rẻ.

## 8. Replication, consistency và thời điểm nhìn thấy dữ liệu

Giả sử cluster production dùng replication factor phù hợp, ví dụ ba replica trong một datacenter. Mỗi page là **một lần đọc** theo yêu cầu và consistency của truy vấn; chuỗi nhiều trang không mặc nhiên là một giao dịch đọc duy nhất.

- `LOCAL_ONE` cần phản hồi từ số replica ít hơn và có thể thấy dữ liệu chưa hội tụ.
- `LOCAL_QUORUM` yêu cầu nhiều replica cùng datacenter hơn tùy RF và trạng thái replica. Đây là một trade-off về latency, availability và bảo đảm đọc.
- Cùng `LOCAL_QUORUM` cho tất cả request **không tạo snapshot xuyên nhiều page** nếu có ghi/xóa đồng thời.
- Nếu ứng dụng ghi ở consistency tương thích rồi đọc, có thể đạt những bảo đảm đọc-ghi mạnh hơn theo mô hình Cassandra; nhưng điều đó vẫn khác với **snapshot isolation cho toàn lịch sử**.

Ví dụ, page 1 đọc trước khi một update được đồng bộ tới replica; page 2 đọc sau khi một hoặc nhiều replica đã nhận update. Cùng query string và paging state không buộc hai page thấy cùng phiên bản dữ liệu.

**Không nhân số hàng theo replication factor.** Ba replica của cùng một partition chứa bản sao của dữ liệu logic; `LIMIT` và page size tính trên result rows, không phải “mỗi replica trả một bản sao”.

## 9. Paging state: điều gì phải giữ nguyên?

Paging state là giá trị **opaque** dùng để tiếp tục **cùng một câu truy vấn**. Khi dùng Java Driver, đặc biệt nếu lưu state qua các HTTP request, cần giữ:

| Thuộc tính | Khi tiếp tục bằng paging state |
| --- | --- |
| CQL statement/biểu thức `SELECT` | Giữ nguyên (gồm projection, `WHERE`, `ORDER BY` và `LIMIT` nếu có). |
| Bind values | Giữ nguyên `account_id`, `event_day`, cận thời gian và các tham số khác. |
| Quyền truy cập | Phải xác thực lại account/tenant được phép đọc. |
| Kiểu trạng thái | Dùng API paging state của driver, không tự đoán bytes. |
| Page size | Nên giữ cùng policy khi tiếp tục; thay đổi tùy tiện có thể làm hành vi khó dự đoán. |
| Query version | Quản lý thay đổi schema/API và tuổi thọ token. |

**Không tái sử dụng state giữa hai request khác nhau về dữ liệu mục tiêu.** Ví dụ, token của account A/ngày 20 không được dùng cho account B/ngày 20; token của `SELECT event_type` không được dùng cho `SELECT event_type, summary`.

### 9.1. State trang kế tiếp không phải vị trí của một dòng đã xử lý dở

Hãy tưởng tượng một protocol page thực có ba hàng:

```text
Page hiện tại:
    row A
    row B
    row C

Paging state S_next -> page kế tiếp, nằm SAU page hiện tại
```

Nếu Java chỉ xử lý `row A` rồi gửi `S_next` cho client, request kế tiếp có thể **bỏ `row B` và `row C`**. Đây là lỗi ứng dụng, không phải do Cassandra không phân trang đúng.

Quy tắc:

- Xử lý/đưa vào response **hết page hiện tại** trước khi cấp token cho page tiếp theo.
- Nếu API chỉ muốn tối đa `N` items nhưng server trả hơn `N` trong một protocol page, phải **buffer** phần dư và lưu trạng thái ứng dụng tương ứng, hoặc thiết kế cơ chế khác; không được âm thầm bỏ phần dư rồi phát token của page sau.
- Một lựa chọn khác: **keyset cursor** theo clustering key, có thể quản lý số hàng hiển thị độc lập với protocol page.

### 9.2. Paging state không phải token bảo mật

Trong Java Driver 4.x, có các API như `PagingState.fromString(...)`, `PagingState.toString()` và `ExecutionInfo.getSafePagingState()`. “Safe” là kiểm tra tính tương ứng với truy vấn/bind values; **không đồng nghĩa token được ký mật mã và an toàn để client tùy ý sửa hoặc chia sẻ**.

Nếu API đưa token qua HTTP:

1. Xác thực/ủy quyền người dùng trước khi đọc Cassandra.
2. Bảo vệ token bằng **HMAC hoặc mã hóa xác thực (AEAD)**, hoặc lưu state phía server và cấp mã tham chiếu ngắn hạn.
3. Ràng buộc tenant/account, ngày, query version, expiration và giới hạn page size của API.
4. Giới hạn chiều dài token; xử lý sai chữ ký, sai định dạng hoặc sai query thành lỗi có kiểm soát, không retry vô hạn.
5. Tránh lưu token nguyên vẹn trong access logs và telemetry nếu không cần.

Đừng nhầm một paging state có thể được parse thành công với **quyền được phép xem dữ liệu**.

## 10. Làm sao giảm biến động giữa các trang?

Không có cách nào biến paging state thành snapshot chỉ bằng một tham số, nhưng có những chiến lược **giảm phạm vi biến động**.

### 10.1. Cố định cận thời gian (as-of)

Giả sử request đầu xác định `asOf = 2026-11-20T15:00:00Z`. Mọi trang dùng cùng điều kiện:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND occurred_at < '2026-11-20 15:00:00+0000'
ORDER BY occurred_at DESC, event_id DESC;
```

Nếu sau đó có sự kiện thật sự mới lúc `16:00`, nó **nằm ngoài điều kiện `WHERE`** của mọi page, làm danh sách được neo theo một cửa sổ thời gian. Các request tiếp theo phải giữ nguyên cận `asOf`.

Tuy nhiên:

- Một sự kiện **ghi muộn với timestamp 11:00** vẫn có thể đi vào tập dữ liệu dù nhỏ hơn `asOf`.
- Xóa, sửa, TTL và replica chưa hội tụ vẫn có thể làm trang thay đổi.
- `asOf` chỉ là **cửa sổ truy vấn**, **không phải snapshot transaction**.

Nếu sản phẩm có yêu cầu “báo cáo đúng trạng thái tại T0”, cần phương án riêng như snapshot/export, event log bất biến, CDC hoặc quy trình đối soát chứ không dựa hoàn toàn vào paging state.

### 10.2. Keyset cursor theo khóa phân cụm

Với bảng có `CLUSTERING ORDER BY (occurred_at DESC, event_id DESC)`, trang đầu:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Trên dữ liệu gốc, dòng cuối trang đầu là `(12:00, ...0005)`. Để lấy các dòng đứng sau theo chiều giảm:

```sql
SELECT occurred_at, event_id, event_type, summary
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 12:00:00+0000',
      00000000-0000-4000-8000-000000000005
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Ở tập dữ liệu gốc, trang tiếp là `PAY/0004`, `CLICK/0003`, `VIEW/0002`. Khi có ghi/xóa giữa hai request, tập dòng vẫn có thể thay đổi, nhưng ứng dụng **hiểu được ranh giới theo khóa** thay vì giữ một state opaque.

**Vì sao cursor phải gồm cả `event_id`?** Hai sự kiện `PAY/0004` và `CLICK/0003` có cùng timestamp 10:00. Nếu một trang kết thúc ở `PAY/0004` mà trang sau chỉ dùng `occurred_at < 10:00`, hàng `CLICK/0003` sẽ bị bỏ qua. Tuple boundary xử lý đúng vị trí theo **đầy đủ clustering key**.

### 10.3. Paging state và keyset có các thế mạnh khác nhau

| Tiêu chí | Paging state | Keyset cursor |
| --- | --- | --- |
| Tiếp tục cùng một truy vấn CQL | Rất phù hợp | Thay `WHERE` bằng ranh giới khóa mới |
| Số hàng UI cố định | Không được bảo đảm chỉ từ page size | Dễ đặt `LIMIT N` cho từng truy vấn, vẫn cần xử lý dữ liệu động |
| Ranh giới nhìn thấy được | Opaque | Bộ clustering key cuối đã trả |
| Trang N ngẫu nhiên | Không hỗ trợ trực tiếp | Cũng không tự nhảy N nếu thiếu ranh giới |
| Dữ liệu đổi giữa các request | Không snapshot | Không snapshot |
| Ràng buộc CQL | Query và bind values phải giữ nguyên | Khóa phân cụm và chiều so sánh phải hợp lệ |
| Token HTTP | Phải bảo vệ state | Cũng phải bảo vệ cursor/tenant/asOf |

Không trộn một paging state cũ với một query `WHERE` đã đổi sang tuple boundary mới: đó không còn là truy vấn tương ứng với state cũ.

## 11. Java Driver 4.x: đọc số hàng thực của một page

Ví dụ sau dùng **Java 17** và **Apache Cassandra Java Driver 4.x**. Giả định có `CqlSession session` kết nối tới `cassandra_page_mutation_lab`.

### 11.1. Tránh đọc tất cả page khi chỉ muốn một page HTTP

```java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.UUID;

PreparedStatement prepared = session.prepare("""
    SELECT occurred_at, event_id, event_type, summary
    FROM events_by_account_day
    WHERE account_id = ?
      AND event_day = ?
    ORDER BY occurred_at DESC, event_id DESC
    """);

UUID accountId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111"
);
LocalDate day = LocalDate.parse("2026-11-20");
BoundStatement bound = prepared.bind(accountId, day)
    .setPageSize(3);

ResultSet result = session.execute(bound);

// Vòng lặp này KHÔNG giới hạn ở một protocol page:
// khi hết page đang có, ResultSet đồng bộ có thể fetch tiếp.
for (Row row : result) {
    System.out.println(row.getString("event_type"));
}
```

Với dữ liệu gốc, vòng lặp có thể in **cả bảy sự kiện**. Nếu đây là endpoint HTTP chỉ muốn một trang, không sử dụng vòng lặp đồng bộ như trên mà không kiểm soát ranh giới fetch.

### 11.2. AsyncResultSet.currentPage() chỉ duyệt trang hiện tại

```java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.util.concurrent.CompletionStage;

CompletionStage<AsyncResultSet> firstFuture =
    session.executeAsync(bound);

CompletionStage<Void> displayFirstPage = firstFuture.thenAccept(page -> {
    int actualRows = 0;
    for (Row row : page.currentPage()) {
        actualRows++;
        System.out.println(row.getString("event_type"));
    }
    System.out.println("Actual rows in page: " + actualRows);
    System.out.println("Has more pages: " + page.hasMorePages());
});
```

Đoạn code đếm **số hàng thật sự được trả ở trang hiện tại**. Nó **không** coi `actualRows` bắt buộc bằng 3, và không fetch trang sau nếu ứng dụng không gọi `fetchNextPage()` hoặc không thực thi request mới bằng state.

### 11.3. Một hàm trả về page HTTP và state tiếp theo

Mẫu dưới đây trả **đúng toàn bộ protocol page hiện tại**, không cố làm “mỗi page HTTP chắc chắn có ba item”. Phần bảo vệ token HTTP được để ở tầng service/gateway; ví dụ **không an toàn để nhận token thô từ người dùng chưa tin cậy**.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PagingState;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

record EventItem(Instant occurredAt, UUID eventId,
                 String eventType, String summary) {}

record EventPage(List<EventItem> items, String nextPageState,
                 int actualRows) {}

static CompletionStage<EventPage> fetchOneProtocolPage(
        CqlSession session,
        PreparedStatement query,
        UUID accountId,
        LocalDate day,
        String verifiedDriverState) {

    BoundStatement stmt = query.bind(accountId, day)
        .setPageSize(3);

    if (verifiedDriverState != null && !verifiedDriverState.isBlank()) {
        // Chỉ nhận state ĐÃ được xác thực và giải mã ở tầng API.
        PagingState state = PagingState.fromString(verifiedDriverState);
        stmt = stmt.setPagingState(state);
    }

    return session.executeAsync(stmt).thenApply(page -> {
        List<EventItem> items = new ArrayList<>();
        for (Row row : page.currentPage()) {
            items.add(new EventItem(
                row.getInstant("occurred_at"),
                row.getUuid("event_id"),
                row.getString("event_type"),
                row.getString("summary")
            ));
        }

        PagingState next = page.hasMorePages()
            ? page.getExecutionInfo().getSafePagingState()
            : null;

        String stateForNext = next == null ? null : next.toString();
        return new EventPage(
            List.copyOf(items), stateForNext, items.size()
        );
    });
}
```

**Cách dùng đúng trong hệ thống thực:**

1. `verifiedDriverState` phải được tách từ **token API đã xác thực**, không lấy raw query string tùy ý từ Internet.
2. Dùng **cùng prepared query và bind values** trong request kế tiếp.
3. Lặp qua **toàn bộ `currentPage()`** trước khi dùng state tiếp theo.
4. Giá trị `actualRows` được dùng cho metrics và UI, **không dùng để quyết định hết dữ liệu**.
5. Khi `page.hasMorePages() == false`, `nextPageState` là null.
6. Nếu `actualRows = 0` và vẫn có state, ứng dụng có thể tiếp tục theo chính sách UX/budget, không biến thành vòng lặp vô hạn trên request HTTP.
7. Nếu cần page UI tối đa N cố định khi protocol trả khác N, phải có cơ chế buffer/cursor đúng ranh giới; không cắt `items` rồi vẫn trả state trỏ sau **cả page**.

### 11.4. Khi chủ động muốn tải trang kế tiếp

```java
session.executeAsync(bound).thenCompose(first -> {
    if (first.hasMorePages()) {
        return first.fetchNextPage();
    }
    return java.util.concurrent.CompletableFuture.completedFuture(first);
}).thenAccept(page -> {
    // page ở đây là page tiếp nếu có, ngược lại là page đầu.
    for (Row row : page.currentPage()) {
        System.out.println(row.getUuid("event_id"));
    }
});
```

Mẫu này chỉ minh họa `fetchNextPage()`. Nếu ứng dụng cần xử lý **cả page đầu lẫn page sau**, phải xử lý page đầu **trước khi** yêu cầu page kế; không dùng đoạn code trên như thể nó đã xuất cả hai page.

## 12. Thiết kế hợp đồng HTTP khi số hàng/page không cố định

Một API “Xem thêm” có thể trả:

```json
{
  "items": [
    {
      "occurredAt": "2026-11-20T14:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000007",
      "eventType": "LOGOUT"
    },
    {
      "occurredAt": "2026-11-20T13:00:00Z",
      "eventId": "00000000-0000-4000-8000-000000000006",
      "eventType": "DELIVER"
    }
  ],
  "actualCount": 2,
  "hasMore": true,
  "nextPageToken": "<opaque-protected-application-token>"
}
```

Đây chỉ là ví dụ **cấu trúc response**, không phải paging token thật hoặc cam kết dữ liệu lab nhất định được chia thành hai dòng. **`hasMore` phải xuất phát từ trạng thái continuation thực tế**, không từ `actualCount < requestedPageSize`.

### 12.1. Ba phương án hợp đồng

| Phương án | Cách làm | Đánh đổi |
| --- | --- | --- |
| **Một protocol page cho một HTTP response** | Trả toàn bộ `currentPage()`, kèm state tiếp theo. | Đơn giản, nhưng số item có thể không cố định. |
| **UI tối đa N item, có buffer** | Nếu protocol page vượt N, lưu các hàng dư cùng trạng thái ở server-side cursor. | Kiểm soát số item, tăng state/TTL/storage của API. |
| **Keyset cursor + `LIMIT N`** | Mỗi HTTP request là query theo boundary khóa kế tiếp. | Phải tự xây cursor/điều kiện khóa, không có snapshot. |

Với endpoint xem lịch sử đơn giản, phương án đầu thường hợp với nút “Xem thêm”. Nếu UX bắt buộc page có đúng N item (trừ trang cuối), cần làm rõ xử lý hàng bị lọc, giới hạn số fetch trong một request và phần dữ liệu đang biến động.

### 12.2. Budget chống quét vô hạn

Khi ứng dụng muốn “nạp đủ 20 item hợp lệ” từ nhiều page, cần trần:

- Tối đa bao nhiêu **protocol pages** được fetch trong một request?
- Tối đa bao nhiêu **milliseconds** và bytes response được phép sử dụng?
- Có cho phép page rỗng nhiều lần liên tiếp không?
- Có bao nhiêu partition trong `WHERE`/`IN` và bao nhiêu request đồng thời?
- Khi hết budget mà vẫn còn state, API trả **ít item + token còn tiếp tục** hay báo trạng thái khác?

Đừng cố fetch cho tới khi đủ 20 bằng mọi giá; nếu 20 item hiếm trong dữ liệu lớn, request có thể phải scan rất rộng và timeout. Trong trường hợp đó, thiết kế bảng/index theo truy vấn hoặc hiển thị page nhỏ là lựa chọn hợp lý hơn.

## 13. Đo đạc và thử nghiệm trên dữ liệu thay đổi

### 13.1. Một kịch bản kiểm tra tái lập được

Trên **môi trường lab**, có thể làm:

1. Tạo keyspace/bảng và nạp mười dòng mẫu ở mục 3.
2. Chạy query account A/ngày 20 với `pageSize = 3`; lưu **những ID thực nhận và state**, không suy sẵn chia 3/3/1.
3. Trước lần fetch tiếp, chạy **một** thay đổi thử nghiệm, ví dụ INSERT sự kiện lúc 15:00.
4. Tiếp tục bằng state tương ứng, ghi các ID và số hàng từng page, so sánh với một query mới từ đầu.
5. Lặp lại trên **lab được reset dữ liệu** với thao tác ghi muộn 11:00, DELETE 10:00/id4 và UPDATE summary.
6. Lặp lại ở các mức consistency phù hợp nếu có cluster nhiều replica.
7. Không dùng số liệu từ một lần chạy để tuyên bố mọi lần paging sẽ giống nhau.

**Không chạy đồng thời tất cả INSERT/DELETE mẫu rồi dùng các kết quả “dữ liệu gốc” ở trên để đối chiếu**, vì bảng lúc đó đã khác. Mỗi thí nghiệm nên có state ban đầu và mốc thời gian ghi rõ ràng.

### 13.2. Metrics nên theo dõi

| Metric | Phản ánh điều gì? |
| --- | --- |
| `requestedPageSize` và `actualRows` | Sự khác biệt giữa page mục tiêu và page thực tế. |
| `hasMorePages`, tỷ lệ trang rỗng | Client có kết luận hết dữ liệu sai không? |
| Số fetch mỗi HTTP request | Có tự động tải nhiều page ngoài ý muốn không? |
| Page latency p50/p95/p99 | Có page chậm do storage, consistency hoặc tải không? |
| Bytes trả về, kích thước row, projection | Cần giảm payload hay không? |
| Tombstone warnings và read amplification | Có đang đọc nhiều dữ liệu hết hiệu lực không? |
| Timeout/unavailable/retry counts | Ảnh hưởng của replica, load và backoff. |
| Số partition ứng viên, độ dài `IN` | Paging đang che giấu một query fan-out lớn không? |
| Số lần token sai/expired/mismatch | Chất lượng hợp đồng API và kiểm soát bảo mật. |

### 13.3. Khi có lỗi, xử lý theo nguyên nhân

- **InvalidQuery:** thiếu điều kiện khóa, `ORDER BY` sai hoặc cú pháp không tương thích; tăng timeout không sửa được.
- **Paging state invalid/mismatch:** token không còn tương ứng query/bind values hoặc bị lỗi; từ chối có kiểm soát, yêu cầu bắt đầu lại nếu phù hợp.
- **Read timeout/Unavailable:** xem consistency, replica, tải, partition size và retry policy; không retry vô hạn.
- **Ít hàng nhưng page chậm:** phân tích tombstone/TTL, filtering, SSTable reads và cột lớn.
- **Hàng thay đổi giữa các page:** kiểm tra thời điểm INSERT/DELETE/UPDATE/TTL, consistency và kỳ vọng snapshot của API.

## 14. Những nhầm lẫn thường gặp

| Nhận định sai | Thực tế | Cách xử lý |
| --- | --- | --- |
| “`pageSize(3)` chắc chắn trả đúng 3 hàng/page.” | Page size là mục tiêu, số thực có thể khác. | Đếm hàng thực và xét `hasMorePages()`. |
| “Page có 2 hàng nên đã hết.” | Có thể vẫn còn paging state. | Không suy `hasMore` từ `items.size()`. |
| “Page rỗng thì không thể có page sau.” | Filtering/tombstone có thể tạo page rỗng còn continuation. | Dùng state, đặt fetch budget. |
| “`LIMIT 5` tức mỗi HTTP page 5 hàng.” | `LIMIT` là trần **toàn câu CQL**. | Phân biệt trần tổng với page size. |
| “`PER PARTITION LIMIT 2` là 2 hàng/trang.” | Đó là giới hạn **mỗi partition** trong result set. | Không reset theo page. |
| “Duyệt `ResultSet` đồng bộ với `setPageSize(3)` chỉ đọc page đầu.” | Iterator có thể tự fetch hết. | Dùng `AsyncResultSet.currentPage()` hoặc kiểm soát fetch. |
| “Có state từ page thì chỉ cần xử lý một hàng đầu.” | State trỏ tới **page sau**, có thể bỏ phần dư. | Xử lý hết page hoặc buffer. |
| “Bổ sung hàng 15:00 chắc xuất hiện ở page kế.” | Nó đứng trước vị trí đã đi qua. | Làm mới danh sách hoặc có luồng cập nhật mới. |
| “INSERT ghi muộn luôn bị loại khỏi trang đang duyệt.” | Nó có thể nằm trong vùng chưa đọc. | Quy định as-of và hiểu không snapshot. |
| “Giữ `WHERE` giống nhau là có snapshot.” | Ghi/xóa/TTL và replica vẫn thay đổi. | Thiết kế snapshot/CDC nếu cần. |
| “`LOCAL_QUORUM` biến nhiều page thành một transaction.” | Consistency không phải snapshot isolation. | Phân biệt read/write guarantees với snapshot. |
| “Chỉ cần timestamp làm keyset cursor.” | Timestamp có thể trùng. | Dùng tuple `(occurred_at,event_id)`. |
| “Token safe của driver đã an toàn để public.” | Safe wrapper không thay cryptographic auth. | Ký/mã hóa, scope và expiry. |
| “`LIMIT`/page size làm `ALLOW FILTERING` rẻ.” | Vẫn có thể quét nhiều hàng trước khi có kết quả. | Giới hạn đường đọc hoặc thiết kế bảng/index. |

## 15. Bài tập thực hành có đáp án

### Bài 1. Chọn tín hiệu hết dữ liệu

**Đề:** API yêu cầu `pageSize = 3`. Java nhận page có **2 hàng**, `hasMorePages() = true`. API có được trả `nextPageToken = null` vì “chưa đủ ba” không?

**Đáp án:** **Không.** Số hàng ít hơn page size không chứng minh đã hết dữ liệu. Nếu state tiếp theo hợp lệ, trả token/`hasMore = true` và cho phép tiếp tục theo chính sách API.

### Bài 2. Số hàng của LIMIT và page size

**Đề:** Trên partition gốc có bảy sự kiện, truy vấn `LIMIT 5` và đặt page size mục tiêu `3`. Tổng số hàng tối đa được trả là bao nhiêu? Trong giả định page đầy đúng mục tiêu, chia thành mấy page?

**Đáp án:** Tổng **năm** hàng. Trong giả định lý tưởng là **hai page: 3 + 2**. Không lấy giả định đó làm một bảo đảm cho tất cả đường thực thi của Cassandra.

### Bài 3. INSERT trước cursor

**Đề:** Client đã nhận `14:00/0007, 13:00/0006, 12:00/0005` rồi hệ thống ghi một sự kiện `15:00/0011`. Có chắc request next sẽ thấy hàng `15:00` không?

**Đáp án:** **Không.** Hàng mới đứng **trước** vị trí đã duyệt của thứ tự giảm dần. Một lần đọc mới từ đầu có thể thấy nó, còn tiếp tục paging không được bảo đảm quay về vùng đầu danh sách.

### Bài 4. DELETE và số hàng trang sau

**Đề:** Sau page đầu, hệ thống xóa `PAY/0004`. Page kế có phải vẫn chứa `0004, 0003, 0002` như dữ liệu gốc không?

**Đáp án:** Không. `0004` có thể không được trả khi lần đọc kế tiếp quan sát việc xóa. Số hàng, nội dung và ranh giới page có thể khác. Paging state không đóng băng dữ liệu tại `T0`.

### Bài 5. Vì sao không được bỏ phần dư page?

**Đề:** Cassandra trả một protocol page gồm 3 hàng `A, B, C`; UI chỉ lấy hai hàng `A, B` nhưng API lại trả state tới **page kế tiếp**. Sai ở đâu?

**Đáp án:** `C` chưa được hiển thị hoặc lưu nhưng state đã bỏ qua **toàn bộ page hiện tại**. Phải trả hết ba hàng, **buffer C** trong cursor ứng dụng, hoặc đổi chiến lược phân trang như keyset. Không được bỏ `C` rồi coi state kế tiếp là vị trí sau `B`.

### Bài 6. As-of có phải snapshot?

**Đề:** Mọi request thêm `AND occurred_at < '2026-11-20 15:00:00+0000'`. Sau đó ứng dụng ghi muộn một sự kiện lúc `11:00`. As-of có chắc chắn loại sự kiện mới không?

**Đáp án:** **Không.** Dù được ghi sau, sự kiện mang timestamp 11:00 vẫn nằm **dưới cận 15:00**. As-of theo timestamp thu hẹp cửa sổ khóa, **không** là snapshot theo thời điểm commit. Muốn trạng thái nhất quán tại T0 phải có cơ chế khác.

### Bài 7. Hai sự kiện cùng timestamp

**Đề:** Trang mới nhất trước kết thúc ở `10:00/0004`. Viết `WHERE` phù hợp để tránh bỏ `10:00/0003` trong trang sau.

**Đáp án:**

```sql
SELECT occurred_at, event_id, event_type
FROM events_by_account_day
WHERE account_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-20'
  AND (occurred_at, event_id) < (
      '2026-11-20 10:00:00+0000',
      00000000-0000-4000-8000-000000000004
  )
ORDER BY occurred_at DESC, event_id DESC
LIMIT 3;
```

Tuple boundary theo full clustering key vẫn cho phép dòng `10:00/0003` được trả; chỉ so sánh `occurred_at < 10:00` sẽ bỏ sót nó.

### Bài 8. Dữ liệu thay đổi nhưng consistency cao

**Đề:** Mọi page đều đọc với `LOCAL_QUORUM` trong cluster RF phù hợp. Có được tuyên bố “đây là snapshot của dữ liệu tại page đầu” không?

**Đáp án:** **Không.** `LOCAL_QUORUM` ràng buộc số replica phải phản hồi và các bảo đảm nhất quán đọc theo mô hình Cassandra; nó **không tạo snapshot isolation xuyên nhiều lần đọc**. Ghi/xóa/TTL có thể xảy ra giữa các page.

## 16. Checklist trước khi triển khai phân trang trên dữ liệu động

1. **Partition:** đã giới hạn đúng full partition key hoặc một tập partition hữu hạn? Có tránh quét quá rộng chỉ nhờ page size không?
2. **Thứ tự:** clustering order và khóa phân biệt timestamp có phù hợp nhu cầu, nhất là khi dùng keyset cursor?
3. **Số lượng:** đã tách rõ page size, số hàng thực nhận, `LIMIT` toàn truy vấn, `PER PARTITION LIMIT` mỗi partition và page UI chưa?
4. **Kết thúc:** đã dùng `hasMorePages()`/state thật thay vì so sánh số hàng với page size để xác định còn dữ liệu chưa?
5. **Không bỏ sót:** đã xử lý hoặc buffer **toàn bộ** protocol page trước khi đưa token tiếp theo cho client chưa?
6. **Biến động:** API có nói rõ dữ liệu có thể thêm/xóa/sửa/hết TTL giữa các page không? Có cần `asOf`, keyset, CDC hay snapshot riêng không?
7. **Consistency:** có hiểu rằng replication/consistency không biến các page thành snapshot transaction không?
8. **Bảo mật token:** token đã được ký/mã hóa hoặc lưu phía server, gắn principal/tenant, query version, expiry, bound values và quyền truy cập chưa?
9. **Ngân sách:** có trần số fetch, bytes, thời gian, concurrency và số page rỗng liên tiếp không?
10. **Quan sát:** đã đo số hàng/page, `hasMore`, p95/p99, tombstones, timeout/retries và lượng bytes với dữ liệu gần production chưa?
11. **Lỗi:** invalid state có được xử lý riêng với query error/timeout, không gây retry storm hoặc truy cập lẫn tenant không?
12. **Hợp đồng UX:** màn hình có chấp nhận “Xem thêm” với số hàng thay đổi không, hay phải triển khai buffer/keyset cho số lượng cố định?

**Ghi nhớ:** Trong Cassandra, **page size không phải số hàng được bảo đảm** và **paging state không phải snapshot**. Hãy dùng tín hiệu continuation thực tế, xử lý hết page trước khi phát token, kiểm soát phạm vi `WHERE`, và xác định kỳ vọng đúng khi có INSERT/DELETE/TTL giữa các lần đọc. Khi API cần sự ổn định cao hoặc ranh giới nghiệp vụ rõ ràng, thiết kế thêm cửa sổ `asOf`, keyset cursor hoặc cơ chế snapshot/đối soát phù hợp.

## Tài liệu tham khảo

- [DataStax Java Driver 4.17 — Paging: synchronous, asynchronous, paging state](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/paging/index.html)
- [Java Driver 4.x — AsyncResultSet API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/AsyncResultSet.html)
- [Java Driver 4.x — PagingState API](https://docs.datastax.com/en/latest-java-driver-api/com/datastax/oss/driver/api/core/cql/PagingState.html)
- [Apache Cassandra Documentation — SELECT, WHERE, LIMIT, PER PARTITION LIMIT và ORDER BY](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html)
- [Apache Cassandra Documentation — Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html)
